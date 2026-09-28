"""全库一键刮削：按书名/作者相似度选最近匹配后写入。"""
from __future__ import annotations

import os
import random
import re
import threading
import time
from difflib import SequenceMatcher
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .importer import ensure_category_tag, relocate_local_txt
from .models import Book
from .scrapers import ALL_SOURCES, REGISTRY, SOURCE_LABELS
from .scrapers.qidian import ScrapeError, clean_tag_token, download_cover
from .config import UNCATEGORIZED, make_category_label, map_site_category, normalize_source, settings


def _env_float(key: str, default: float) -> float:
    raw = (os.environ.get(key) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = (os.environ.get(key) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# 书与书之间的基础间隔（秒）；过大容易拖慢，过小易触发起点 WAF
_BASE_DELAY = max(0.3, _env_float("SCRAPER_DELAY", 2.0))
# 在基础间隔上随机抖动（秒），避免固定节拍被识别为脚本
_JITTER_MAX = max(0.0, _env_float("SCRAPER_JITTER_MAX", 1.5))
# 每完成 N 本插入一次「像人休息」的长间隔；0 = 关闭
_LONG_PAUSE_EVERY = max(0, _env_int("SCRAPER_LONG_PAUSE_EVERY", 10))
_LONG_PAUSE_MIN = max(3.0, _env_float("SCRAPER_LONG_PAUSE_MIN", 6.0))
_LONG_PAUSE_MAX = max(_LONG_PAUSE_MIN, _env_float("SCRAPER_LONG_PAUSE_MAX", 12.0))
# 被拦截后的退避序列（秒），超过则取最后一档
_BACKOFF_STEPS = [5.0, 15.0, 60.0]
# 连续被拦达到该次数则熔断暂停
_BLOCK_BREAK_AT = max(2, _env_int("SCRAPER_BLOCK_BREAK_AT", 3))
# 熔断冷却时长（秒）
_BLOCK_BREAK_SECONDS = max(30.0, _env_float("SCRAPER_BLOCK_BREAK_SECONDS", 180.0))

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
# 请求中止批量刮削（A6）
_cancel = threading.Event()


def get_batch_status() -> dict:
    out = dict(_status)
    out["log"] = list(_status.get("log") or [])
    out["cancel_requested"] = _cancel.is_set()
    return out


def request_batch_cancel() -> bool:
    if not _status.get("running"):
        return False
    _cancel.set()
    return True


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
    # 从书名里的「作者：xxx」提取作者，否则回退本地作者
    m = re.search(r"作者\s*[：:]\s*([^\s》）)]+)", title or "")
    if m:
        return m.group(1).strip()
    return fallback or ""


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
    # 站外字数写入（0 表示未取到，保留本地统计）
    try:
        wc = int(hit_dict.get("word_count") or 0)
        if wc > 0:
            book.word_count = wc
    except (TypeError, ValueError):
        pass
    # 分类写成「书源-站内分类」；与单本刮削一致（map_site_category 统一匹配）
    if hit_dict.get("category"):
        raw_cat = (hit_dict["category"] or "").strip()[:50]
        src = normalize_source(hit_dict.get("source") or "")
        src_n, cat_n = map_site_category(src, raw_cat)
        book.category = make_category_label(src_n, cat_n)
    elif not book.category:
        book.category = UNCATEGORIZED

    raw_tags = list(hit_dict.get("tags") or [])
    cleaned = []
    for t in raw_tags:
        tok = ctt(t)
        if tok and tok not in cleaned and tok != UNCATEGORIZED:
            cleaned.append(tok)
    # 已正式分类则去掉「未分类」标记
    book.tags = ensure_category_tag(",".join(cleaned[:12]), book.category)

    book.source = normalize_source(hit_dict.get("source") or "") or book.source or "起点"
    book.source_id = str(hit_dict.get("source_id") or "")

    # 本地 TXT 归位到 novels/<书源>/<分类>/
    relocate_local_txt(book)

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


def _scrape_one(
    db: Session,
    mod,
    label: str,
    book: Book,
    *,
    min_score: float,
    dry_run: bool,
) -> str:
    """刮削单本并写入。返回 skip|preview|ok；失败抛异常。"""
    title, author = book.title, book.author
    search_kw = _search_keyword(title)
    match_author = _author_from_title_field(title, author) or author
    # enrich=False：批量不再给搜索结果补详情，单本请求量从约 8～15 降到 2～4
    hits = mod.search(search_kw or title, limit=8, enrich=False)
    fake_book = Book(title=search_kw or title, author=match_author)
    hit, score = pick_best_hit(fake_book, hits, min_score=min_score)
    if not hit:
        _log(f"跳过《{title}》无足够匹配（最佳 {score:.2f}）")
        return "skip"
    hd = _hit_to_dict(hit)
    src_id = str(hd.get("source_id") or "")
    preview = f"《{title}》→《{hd.get('name')}》/{hd.get('author')} 分数{score:.2f} id={src_id}"
    if dry_run:
        _log(f"[预览] {preview}")
        return "preview"
    # 详情 + 写入（与单本一致）
    detail_blocked = False
    try:
        detail = mod.fetch_detail(src_id)
        d = detail.to_dict()
        for k in ("name", "author", "intro", "status", "cover_url", "latest_chapter", "tags", "category", "word_count"):
            if not d.get(k) and hd.get(k):
                d[k] = hd[k]
        d["source"] = label
        d["source_id"] = src_id or d.get("source_id")
    except ScrapeError as e:
        d = dict(hd)
        d["source"] = label
        d.setdefault("source_id", src_id)
        _log(f"《{title}》详情失败，用搜索结果回退：{e}")
        detail_blocked = bool(getattr(e, "blocked", False))
    _apply_hit_to_book(db, book, d)
    db.commit()
    _log(f"完成 {preview}")
    return "blocked_ok" if detail_blocked else "ok"


def run_batch_scrape(
    source: str = "qidian",
    only_missing: bool = True,
    min_score: float = 0.55,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """同步执行一批刮削（供后台线程调用）。

    默认 HTTP；阶段1 失败项汇总后，若开启浏览器兜底则用 Playwright/CDP 重试。
    """
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
        _status["browser_retried"] = 0
        _status["browser_recovered"] = 0

        # 风控退避状态：连续被拦计数 + 当前退避档位
        block_streak = 0
        backoff_idx = 0
        # HTTP 阶段失败清单，留给浏览器兜底
        failed_jobs: list[tuple[int, str]] = []

        for book in books:
            # 支持中途取消（A6）
            if _cancel.is_set():
                _log("（已取消）")
                break
            _status["done"] += 1
            title = book.title
            try:
                result = _scrape_one(db, mod, label, book, min_score=min_score, dry_run=dry_run)
                if result == "skip":
                    _status["skipped"] += 1
                    block_streak = 0
                elif result == "preview":
                    _status["matched"] += 1
                    block_streak = 0
                    backoff_idx = 0
                elif result == "blocked_ok":
                    _status["matched"] += 1
                    block_streak += 1
                else:
                    _status["matched"] += 1
                    block_streak = 0
                    backoff_idx = 0
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _status["failed"] += 1
                failed_jobs.append((book.id, title))
                blocked = bool(getattr(exc, "blocked", False))
                if blocked:
                    block_streak += 1
                    _log(f"失败《{title}》(风控拦截 # {block_streak}): {exc}")
                    if block_streak >= _BLOCK_BREAK_AT:
                        _log(
                            f"连续 {block_streak} 次被拦截，暂停 {_BLOCK_BREAK_SECONDS:.0f}s 冷却后继续…"
                        )
                        _cancel.wait(_BLOCK_BREAK_SECONDS)
                        if _cancel.is_set():
                            _log("（已取消）")
                            break
                        block_streak = 0
                        backoff_idx = 0
                else:
                    block_streak = 0
                    _log(f"失败《{title}》: {exc}")

            if _cancel.is_set():
                break
            # 间隔：2s 基准 + 随机抖动；被拦时改为指数退避；偶发长休息更像真人
            delay = _BASE_DELAY + random.uniform(0.0, _JITTER_MAX)
            if block_streak > 0:
                step = _BACKOFF_STEPS[min(backoff_idx, len(_BACKOFF_STEPS) - 1)]
                backoff_idx = min(backoff_idx + 1, len(_BACKOFF_STEPS) - 1)
                delay = step
                _log(f"风控退避，等待 {delay:.0f}s…")
            elif (
                _LONG_PAUSE_EVERY > 0
                and _status["done"] > 0
                and _status["done"] % _LONG_PAUSE_EVERY == 0
            ):
                pause = random.uniform(_LONG_PAUSE_MIN, _LONG_PAUSE_MAX)
                delay += pause
                _log(f"节奏暂停 {pause:.1f}s（每 {_LONG_PAUSE_EVERY} 本）")
            time.sleep(delay)

        # 阶段2：汇总 HTTP 失败项，用浏览器（CDP）兜底重试
        if failed_jobs and not dry_run and not _cancel.is_set():
            _run_browser_fallback(db, mod, label, failed_jobs, min_score=min_score)

        summary = (
            f"共 {_status['total']} 本 · 写入 {_status['matched']} · "
            f"跳过 {_status['skipped']} · 失败 {_status['failed']}"
            + (f" · 浏览器兜底恢复 {_status['browser_recovered']}" if _status.get("browser_retried") else "")
            + ("（预览）" if dry_run else "")
        )
        _log(summary)
        return dict(_status)
    finally:
        db.close()


def _run_browser_fallback(
    db: Session,
    mod,
    label: str,
    failed_jobs: list[tuple[int, str]],
    *,
    min_score: float,
) -> None:
    """失败汇总后用 Playwright/CDP 重试（fnOS tieron Chrome）。"""
    from .scrapers import http_util
    from .scrapers.browser_fallback import (
        browser_fallback_enabled,
        ensure_browser_ready,
        last_browser_error,
    )

    if not browser_fallback_enabled():
        _log(f"失败 {len(failed_jobs)} 本未重试（未开 SCRAPER_BROWSER_FALLBACK）")
        return
    _log(f"HTTP 阶段失败 {len(failed_jobs)} 本，唤醒浏览器并兜底重试…")
    if not ensure_browser_ready():
        _log(f"浏览器未就绪，保留失败待人工处理：{last_browser_error()}")
        return

    http_util.set_browser_mode(True)
    try:
        for book_id, title in failed_jobs:
            if _cancel.is_set():
                _log("（已取消）")
                break
            book = db.get(Book, book_id)
            if not book:
                continue
            _status["browser_retried"] = _status.get("browser_retried", 0) + 1
            try:
                result = _scrape_one(db, mod, label, book, min_score=min_score, dry_run=False)
                if result in ("ok", "blocked_ok"):
                    _status["browser_recovered"] = _status.get("browser_recovered", 0) + 1
                    # 成功则从 failed 计数里扣回
                    _status["failed"] = max(0, _status["failed"] - 1)
                    _log(f"[浏览器] 恢复《{title}》")
                elif result == "skip":
                    _log(f"[浏览器] 《{title}》仍无匹配")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _log(f"[浏览器] 《{title}》仍失败: {exc}")
            time.sleep(_BASE_DELAY + random.uniform(0.0, _JITTER_MAX))
    finally:
        http_util.set_browser_mode(False)
        _log("浏览器兜底阶段结束")


def start_batch_scrape(**kwargs) -> bool:
    if not _lock.acquire(blocking=False):
        return False
    if _status.get("running"):
        _lock.release()
        return False
    _cancel.clear()

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
