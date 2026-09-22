"""全库一键刮削：按书名/作者相似度选最近匹配后写入。"""
from __future__ import annotations

import re
import threading
import time
from difflib import SequenceMatcher
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Book
from .scrapers import REGISTRY, SOURCE_LABELS
from .scrapers.qidian import ScrapeError, clean_tag_token, download_cover
from .config import settings

_lock = threading.Lock()
_status: dict = {
    "running": False,
    "total": 0,
    "done": 0,
    "matched": 0,
    "skipped": 0,
    "failed": 0,
    "log": [],
    "last_error": "",
}


def get_batch_status() -> dict:
    out = dict(_status)
    out["log"] = list(_status.get("log") or [])
    return out


def _log(msg: str) -> None:
    _status["log"].append({"time": datetime.now().isoformat(timespec="seconds"), "message": msg})
    del _status["log"][:-80]


def _search_keyword(title: str) -> str:
    """批量搜索用的干净书名：去 《》、（校对版全本）、作者：xxx 等。"""
    s = (title or "").strip()
    s = re.sub(r"作者\s*[：:]\s*\S+\s*$", "", s)
    s = re.sub(r"[（(][^（()）]{0,20}?(校对|精校|全本|修订|完本|作品|著)[^（()）]{0,10}[）)]", "", s)
    s = re.sub(r"[《》〈〉\[\]【】]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or (title or "").strip()


def _author_from_title_field(title: str, fallback: str) -> str:
    m = re.search(r"作者\s*[：:]\s*([^\s》）)]+)", title or "")
    if m:
        return m.group(1).strip()
    return fallback or ""
    s = (s or "").strip()
    s = re.sub(r"[《》〈〉\[\]【】()（）]", "", s)
    s = re.sub(r"(校对版全本|全本|精校版|修订版)$", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _norm_name(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"作者\s*[：:]\s*\S+\s*$", "", s)
    s = re.sub(r"[《》〈〉\[\]【】()（）]", "", s)
    s = re.sub(r"(校对版全本|校对版|精校版|全本|修订版|完本)", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _norm_author(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"(著|作品|文)$", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def score_match(local_title: str, local_author: str, hit_title: str, hit_author: str) -> float:
    """0~1，书名为主、作者为辅。"""
    lt, ht = _norm_name(local_title), _norm_name(hit_title)
    la, ha = _norm_author(local_author), _norm_author(hit_author)
    if not lt or not ht:
        return 0.0
    if lt == ht:
        title_score = 1.0
    elif lt in ht or ht in lt:
        title_score = 0.85
    else:
        title_score = SequenceMatcher(None, lt, ht).ratio()
        # 过短/过长惩罚
        if min(len(lt), len(ht)) < 2:
            title_score *= 0.5

    author_score = 0.5  # 未知作者中性分
    if la and ha:
        if la == ha:
            author_score = 1.0
        elif la in ha or ha in la:
            author_score = 0.85
        else:
            author_score = SequenceMatcher(None, la, ha).ratio()
    elif la or ha:
        author_score = 0.55

    # 书名权重 0.75，作者 0.25
    return round(title_score * 0.75 + author_score * 0.25, 4)


def pick_best_hit(book: Book, hits: list, min_score: float = 0.55):
    scored = []
    for h in hits or []:
        sc = score_match(book.title, book.author, getattr(h, "name", "") or (h.get("name") if isinstance(h, dict) else ""), getattr(h, "author", "") or (h.get("author") if isinstance(h, dict) else ""))
        scored.append((sc, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return None, 0.0
    best_score, best = scored[0]
    if best_score < min_score:
        return None, best_score
    return best, best_score


def _hit_to_dict(h) -> dict:
    if hasattr(h, "to_dict"):
        return h.to_dict()
    return dict(h)


def _apply_hit_to_book(db: Session, book: Book, hit_dict: dict) -> None:
    """与单本刮削一致的写入逻辑。"""
    from .scrapers.qidian import clean_tag_token as ctt

    if hit_dict.get("name"):
        book.title = hit_dict["name"][:200]
    if hit_dict.get("author"):
        book.author = hit_dict["author"][:100]
    if hit_dict.get("intro"):
        book.intro = hit_dict["intro"]
    st = hit_dict.get("status") or ""
    if st in ("连载", "完结", "未知"):
        book.status = st
    if hit_dict.get("latest_chapter"):
        book.latest_chapter = hit_dict["latest_chapter"][:200]
    if hit_dict.get("category"):
        book.category = hit_dict["category"][:50]

    raw_tags = list(hit_dict.get("tags") or [])
    cleaned = []
    for t in raw_tags:
        tok = ctt(t)
        if tok and tok not in cleaned:
            cleaned.append(tok)
    book.tags = ",".join(cleaned[:12])

    book.source = hit_dict.get("source") or "起点"
    book.source_id = str(hit_dict.get("source_id") or "")

    if hit_dict.get("cover_url"):
        try:
            if book.cover_file:
                old = settings.covers_dir / book.cover_file
                if old.is_file():
                    old.unlink()
            settings.covers_dir.mkdir(parents=True, exist_ok=True)
            tmp = settings.covers_dir / f"{book.id}_scrape_{int(time.time())}"
            ext = download_cover(hit_dict["cover_url"], tmp)
            final = settings.covers_dir / f"{book.id}_scrape_{int(time.time())}{ext}"
            tmp.replace(final)
            book.cover_file = final.name
        except ScrapeError:
            pass

    book.updated_at = datetime.now().isoformat(timespec="seconds")


def run_batch_scrape(
    source: str = "qidian",
    only_missing: bool = True,
    min_score: float = 0.55,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """同步执行一批刮削（供后台线程调用）。"""
    mod = REGISTRY.get(source) or REGISTRY.get("qidian")
    label = SOURCE_LABELS.get(source, "起点")
    db = SessionLocal()
    try:
        stmt = select(Book).order_by(Book.id)
        if only_missing:
            stmt = stmt.where((Book.source == "") | (Book.source.is_(None)) | (Book.source_id == ""))
        books = db.execute(stmt).scalars().all()
        if limit:
            books = books[:limit]

        _status["total"] = len(books)
        _status["done"] = 0
        _status["matched"] = 0
        _status["skipped"] = 0
        _status["failed"] = 0
        _status["dry_run"] = dry_run

        for book in books:
            _status["done"] += 1
            title, author = book.title, book.author
            search_kw = _search_keyword(title)
            match_author = _author_from_title_field(title, author) or author
            try:
                hits = mod.search(search_kw or title, limit=8)
                fake_book = Book(title=search_kw or title, author=match_author)
                hit, score = pick_best_hit(fake_book, hits, min_score=min_score)
                if not hit:
                    _status["skipped"] += 1
                    _log(f"跳过《{title}》无足够匹配（最佳 {score:.2f}）")
                    continue
                hd = _hit_to_dict(hit)
                src_id = str(hd.get("source_id") or "")
                preview = f"《{title}》→《{hd.get('name')}》/{hd.get('author')} 分数{score:.2f} id={src_id}"
                if dry_run:
                    _status["matched"] += 1
                    _log(f"[预览] {preview}")
                    continue

                # 详情 + 写入（与单本一致）
                try:
                    detail = mod.fetch_detail(src_id)
                    d = detail.to_dict()
                    # 合并搜索 hint
                    for k in ("name", "author", "intro", "status", "cover_url", "latest_chapter", "tags", "category"):
                        if not d.get(k) and hd.get(k):
                            d[k] = hd[k]
                    d["source"] = label
                    d["source_id"] = src_id or d.get("source_id")
                except ScrapeError as e:
                    d = dict(hd)
                    d["source"] = label
                    d.setdefault("source_id", src_id)
                    _log(f"《{title}》详情失败，用搜索结果回退：{e}")

                _apply_hit_to_book(db, book, d)
                db.commit()
                _status["matched"] += 1
                _log(f"完成 {preview}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _status["failed"] += 1
                _log(f"失败《{title}》: {exc}")
            time.sleep(0.6)  # 限速，降低风控

        summary = (
            f"共 {_status['total']} 本 · 写入 {_status['matched']} · "
            f"跳过 {_status['skipped']} · 失败 {_status['failed']}"
            + ("（预览）" if dry_run else "")
        )
        _log(summary)
        return dict(_status)
    finally:
        db.close()


def start_batch_scrape(**kwargs) -> bool:
    if not _lock.acquire(blocking=False):
        return False
    if _status.get("running"):
        _lock.release()
        return False

    def _run() -> None:
        _status["running"] = True
        _status["last_error"] = ""
        _status["started_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            run_batch_scrape(**kwargs)
        except Exception as exc:  # noqa: BLE001
            _status["last_error"] = str(exc)
            _log(f"批处理异常: {exc}")
        finally:
            _status["running"] = False
            _lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return True
