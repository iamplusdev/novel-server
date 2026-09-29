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
from .importer import ensure_category_tag
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
    import logging

    logging.getLogger("batch_scrape").info("%s", msg)
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


def pick_best_hit(book: Book, hits: list, min_score: float = 0.8):
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

    # 不在此处移动 TXT；仅「体检 → 按分类归位」触发 relocate

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


def _resolve_source_list(source: str) -> list[tuple[str, object, str]]:
    """把 source 参数解析为按顺序的 [(key, mod, label), ...]。

    source="all"/"全部" 时按 起点 → 番茄 → 纵横 顺序；命中即停。
    """
    raw = (source or "all").strip().lower()
    if raw in ("all", "*", "全部", ""):
        keys: list[str] = list(ALL_SOURCES)
    else:
        keys = [source]
    out: list[tuple[str, object, str]] = []
    for k in keys:
        mod = REGISTRY.get(k) or REGISTRY.get((k or "").strip().lower())
        if not mod:
            continue
        label = SOURCE_LABELS.get(k, SOURCE_LABELS.get((k or "").strip().lower(), k))
        out.append((k, mod, label))
    return out


def _scrape_one(
    db: Session,
    mod,
    label: str,
    book: Book,
    *,
    min_score: float,
) -> str:
    """在指定书源上刮削单本并写入。返回 skip|ok|blocked_ok；失败抛异常。"""
    title, author = book.title, book.author
    search_kw = _search_keyword(title)
    match_author = _author_from_title_field(title, author) or author
    # enrich=False：批量不再给搜索结果补详情，单本请求量从约 8～15 降到 2～4
    hits = mod.search(search_kw or title, limit=8, enrich=False)
    fake_book = Book(title=search_kw or title, author=match_author)
    hit, score = pick_best_hit(fake_book, hits, min_score=min_score)
    if not hit:
        _log(f"《{title}》[{label}] 无足够匹配（最佳 {score:.2f}）")
        return "skip"
    hd = _hit_to_dict(hit)
    src_id = str(hd.get("source_id") or "")
    preview = f"《{title}》[{label}]→《{hd.get('name')}》/{hd.get('author')} 分数{score:.2f} id={src_id}"
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


def _scrape_book_across(
    db: Session,
    book: Book,
    source_pairs: list[tuple[str, object, str]],
    *,
    min_score: float,
) -> str:
    """按书源顺序刮削：任一源 score≥阈值 即写入并停止，不再尝试后续书源。"""
    last_skip = "skip"
    for _key, mod, label in source_pairs:
        if _cancel.is_set():
            return "skip"
        try:
            result = _scrape_one(db, mod, label, book, min_score=min_score)
        except ScrapeError as e:
            # 当前源失败（含风控）则试下一源
            _log(f"《{book.title}》[{label}] 失败: {e}")
            last_skip = "fail"
            if bool(getattr(e, "blocked", False)):
                raise
            continue
        if result == "skip":
            last_skip = "skip"
            continue
        # 命中（ok / blocked_ok）立刻返回，不再用下一书源
        return result
    return last_skip


def run_batch_scrape(
    source: str = "all",
    only_missing: bool = True,
    min_score: float = 0.8,
    limit: int | None = None,
    book_ids: list[int] | None = None,
    mode: str = "auto",
) -> dict:
    """同步执行一批刮削（供后台线程调用）。

    source="all" 时按 起点→番茄→ 纵横 顺序匹配，命中即停；
    book_ids 非空时只刮削指定书（书库多选批量刮削）；
    mode：api=仅 HTTP / chrome=fnOS 浏览器 / auto=HTTP 失败后浏览器兜底。
    """
    from .scrapers import http_util
    from .scrapers.mode import MODE_API, MODE_CHROME, normalize_mode

    scrape_mode = normalize_mode(mode)
    _status["mode"] = scrape_mode
    # chrome：全程走浏览器；api：全程 HTTP；auto：阶段1 HTTP + 阶段2 兜底
    if scrape_mode == MODE_CHROME:
        http_util.set_browser_mode(True)
    else:
        http_util.set_browser_mode(False)

    source_pairs = _resolve_source_list(source)
    if not source_pairs:
        raise ValueError(f"暂不支持的刮削源: {source}")
    src_names = "→".join(label for _, _, label in source_pairs)
    _log(f"刮削源顺序：{src_names}（阈值 {min_score}，命中即停）")
    db = SessionLocal()
    try:
        stmt = select(Book).order_by(Book.id)
        if book_ids:
            # 定向批量：仅处理前端多选的书
            ids = sorted({int(i) for i in book_ids if i})
            stmt = stmt.where(Book.id.in_(ids))
        elif only_missing:
            stmt = stmt.where((Book.source == "") | (Book.source.is_(None)) | (Book.source_id == ""))
        books = db.execute(stmt).scalars().all()
        if limit:
            books = books[:limit]

        _status["total"] = len(books)
        _status["done"] = 0
        _status["matched"] = 0
        _status["skipped"] = 0
        _status["failed"] = 0
        _status["source"] = source
        _status["min_score"] = min_score
        _status["browser_retried"] = 0
        _status["browser_recovered"] = 0

        # 风控退避状态：连续被拦计数 + 当前退避档位
        block_streak = 0
        backoff_idx = 0
        # HTTP 阶段失败清单，留给浏览器兜底（取主书源做重试）
        failed_jobs: list[tuple[int, str]] = []
        primary_mod, primary_label = source_pairs[0][1], source_pairs[0][2]

        for book in books:
            # 支持中途取消（A6）
            if _cancel.is_set():
                _log("（已取消）")
                break
            _status["done"] += 1
            title = book.title
            try:
                result = _scrape_book_across(db, book, source_pairs, min_score=min_score)
                if result == "skip":
                    _status["skipped"] += 1
                    block_streak = 0
                elif result == "fail":
                    _status["failed"] += 1
                    failed_jobs.append((book.id, title))
                    block_streak = 0
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

        # 阶段2：汇总 HTTP 失败项，用浏览器（CDP）兜底重试（api 模式跳过）
        if failed_jobs and not _cancel.is_set() and scrape_mode != MODE_API:
            _run_browser_fallback(db, primary_mod, primary_label, failed_jobs, min_score=min_score)

        summary = (
            f"共 {_status['total']} 本 · 写入 {_status['matched']} · "
            f"跳过 {_status['skipped']} · 失败 {_status['failed']}"
            + (f" · 浏览器兜底恢复 {_status['browser_recovered']}" if _status.get("browser_retried") else "")
        )
        _log(summary)
        return dict(_status)
    finally:
        if scrape_mode == MODE_CHROME:
            from .scrapers import http_util as _hu

            _hu.set_browser_mode(False)
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
