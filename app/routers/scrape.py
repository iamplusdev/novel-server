"""刮削 API：搜索站外元数据并写回本地书籍。"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..config import UNCATEGORIZED, make_category_label, map_site_category, normalize_source, settings
from ..database import get_db
from ..importer import ensure_category_tag
from ..models import Book
from ..scrapers import REGISTRY, SOURCE_LABELS
from ..scrapers.mode import (
    MODE_API,
    MODE_AUTO,
    MODE_CHROME,
    describe_modes,
    get_scrape_mode,
    normalize_mode,
    set_scrape_mode,
)
from ..serializers import admin_book_detail


def category_label_from_hit(source: str, raw: str) -> str:
    """站内分类 → 存储用「书源-分类」（自动/手动刮削共用匹配）。"""
    src, cat = map_site_category(source, raw)
    return make_category_label(src, cat)


router = APIRouter(prefix="/api/admin/scrape", tags=["scrape"], dependencies=[Depends(require_admin_dep)])


class SearchIn(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=80)
    source: str = Field(default="qidian", max_length=20)
    limit: int = Field(default=10, ge=1, le=20)
    # 取数方式：api=HTTP / chrome=fnOS 浏览器 / auto=检测 Chrome 优先，失败回退 API
    mode: str = Field(default="auto", max_length=20)


class ApplyIn(BaseModel):
    source: str = Field(default="qidian", max_length=20)
    source_book_id: str = Field(..., min_length=1, max_length=32)
    keyword: str | None = Field(default=None, max_length=80)
    with_cover: bool = True
    # 取数方式：api / chrome / auto（Chrome 优先，失败回退 API）
    mode: str = Field(default="auto", max_length=20)
    # 搜索列表里已有的字段，详情被风控时可作回退
    hint_name: str | None = Field(default=None, max_length=200)
    hint_author: str | None = Field(default=None, max_length=100)
    hint_intro: str | None = Field(default=None, max_length=1000)
    hint_status: str | None = Field(default=None, max_length=20)
    hint_cover_url: str | None = Field(default=None, max_length=500)
    hint_tags: list[str] | None = None
    hint_category: str | None = Field(default=None, max_length=50)
    # 宽松整型：兼容 "120000"、浮点串，脏数据归 0
    hint_word_count: int = Field(default=0, ge=0)

    @field_validator("hint_word_count", mode="before")
    @classmethod
    def _coerce_word_count(cls, v):
        if v is None or v == "":
            return 0
        try:
            n = int(float(str(v).strip()))
        except (TypeError, ValueError):
            return 0
        return max(0, n)


def _mod(source: str):
    mod = REGISTRY.get((source or "").strip().lower()) or REGISTRY.get((source or "").strip())
    if not mod:
        raise HTTPException(400, f"暂不支持的刮削源: {source}")
    return mod


def _with_mode(mode: str, fn):
    """按刮削方式执行 fn()：api=HTTP，chrome=浏览器，auto=检测 Chrome 优先、失败回退 API。"""
    from ..scrapers import http_util
    from ..scrapers.qidian import ScrapeError

    m = normalize_mode(mode)
    if m == MODE_CHROME:
        http_util.set_browser_mode(True)
        try:
            return fn()
        except ScrapeError as e:
            raise HTTPException(502, str(e)) from e
        finally:
            http_util.set_browser_mode(False)
    if m == MODE_API:
        http_util.set_browser_mode(False)
        try:
            return fn()
        except ScrapeError as e:
            raise HTTPException(502, str(e)) from e
    # auto：检测到 fnOS Chrome 则优先浏览器，失败回退 API；未检测到则纯 API
    try:
        from ..scrapers.browser_fallback import chrome_available
    except Exception:  # noqa: BLE001
        chrome_available = None  # type: ignore[assignment]
    use_chrome = bool(chrome_available and chrome_available())
    if use_chrome:
        http_util.set_browser_mode(True)
        try:
            return fn()
        except ScrapeError as first_err:
            # Chrome 优先但失败：回退 API 一次
            http_util.set_browser_mode(False)
            try:
                return fn()
            except ScrapeError as second_err:
                raise HTTPException(
                    502,
                    f"刮削失败（Chrome 与 API 均不可用）：{first_err}；{second_err}",
                ) from second_err
        finally:
            http_util.set_browser_mode(False)
    # 无 Chrome：纯 API
    http_util.set_browser_mode(False)
    try:
        return fn()
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/modes")
def scrape_modes() -> dict:
    """可选刮削方式 + 当前偏好。"""
    return {
        "current": get_scrape_mode(),
        "items": describe_modes(),
        "browser_ready": _browser_ready(),
    }


@router.post("/mode")
def scrape_set_mode(payload: dict) -> dict:
    """设置默认刮削方式（会话级）。"""
    m = set_scrape_mode(str(payload.get("mode") or "auto"))
    return {"ok": True, "current": m}


def _browser_ready() -> bool:
    try:
        from ..scrapers.browser_fallback import probe_cdp

        return probe_cdp(timeout=1.5)
    except Exception:  # noqa: BLE001
        return False


@router.post("/search")
def scrape_search(payload: SearchIn) -> dict:
    mod = _mod(payload.source)

    def _run():
        return mod.search(payload.keyword, limit=payload.limit)

    hits = _with_mode(payload.mode, _run)
    label = SOURCE_LABELS.get(payload.source.strip().lower(), payload.source)
    return {
        "source": label,
        "source_key": payload.source,
        "query": payload.keyword,
        "items": [h.to_dict() for h in hits],
        "count": len(hits),
        "mode": normalize_mode(payload.mode),
    }


@router.post("/detail")
def scrape_detail(payload: ApplyIn) -> dict:
    mod = _mod(payload.source)
    raw = (payload.source_book_id or "").strip()
    extract = getattr(mod, "extract_book_id", None)
    bid = (extract(raw) if extract else raw) or raw

    def _run():
        return mod.fetch_detail(bid)

    hit = _with_mode(payload.mode, _run)
    data = hit.to_dict()
    data["mode"] = normalize_mode(payload.mode)
    return data


@router.post("/books/{book_id}/apply")
def scrape_apply(book_id: int, payload: ApplyIn, db: Session = Depends(get_db)) -> dict:
    from ..scrapers.qidian import ScrapeError

    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    mod = _mod(payload.source)
    label = SOURCE_LABELS.get((payload.source or "qidian").strip().lower(), "起点")

    sid = (payload.source_book_id or "").strip()
    taken = db.execute(
        select(Book).where(Book.source_id == sid, Book.source == label, Book.id != book_id)
    ).scalars().first()
    if taken:
        raise HTTPException(
            409,
            f"{label} ID {sid} 已绑定到《{taken.title}》(ID {taken.id})，请勿重复刮削到多本书",
        )

    hit = None
    detail_err = ""
    try:
        hit = _with_mode(payload.mode, lambda: mod.fetch_detail(payload.source_book_id))
    except (ScrapeError, HTTPException) as e:
        detail_err = str(e)
        # 按当前刮削源构造回退骨架，避免番茄任务落到起点 URL
        from ..scrapers.qidian import ScrapeHit as BaseHit

        book_url = getattr(mod, "book_url_for", None)
        fallback_url = book_url(payload.source_book_id) if book_url else ""
        hit = BaseHit(
            source=getattr(mod, "SOURCE_NAME", label),
            source_id=payload.source_book_id,
            url=fallback_url,
        )

    # 合并 hint（详情优先；详情为空或是 SEO 文案时用搜索结果）
    from ..scrapers.zongheng import _is_seo_intro as _seo_intro

    if not hit.name and payload.hint_name:
        hit.name = payload.hint_name
    if not hit.author and payload.hint_author:
        hit.author = payload.hint_author
    if (not hit.intro or _seo_intro(hit.intro)) and payload.hint_intro:
        hit.intro = payload.hint_intro
    if not hit.status and payload.hint_status:
        s = (payload.hint_status or "").strip()
        hit.status = "完结" if s in ("完结", "已完结", "完本") else ("连载" if s.startswith("连载") else s)
    if not hit.cover_url and payload.hint_cover_url:
        hit.cover_url = payload.hint_cover_url
    if not getattr(hit, "word_count", 0) and payload.hint_word_count:
        hit.word_count = int(payload.hint_word_count or 0)
    if not getattr(hit, "category", "") and payload.hint_category:
        hit.category = payload.hint_category

    if not hit.name and not hit.author:
        raise HTTPException(502, detail_err or "未能获取书籍信息")

    if hit.name:
        book.title = hit.name[:200]
    if hit.author:
        book.author = hit.author[:100]
    if hit.intro:
        book.intro = hit.intro
    if hit.status in ("连载", "完结", "未知"):
        book.status = hit.status
    if hit.latest_chapter:
        book.latest_chapter = hit.latest_chapter[:200]
    # 站外字数写入（0 表示未取到，保留本地统计）
    if getattr(hit, "word_count", 0):
        try:
            wc = int(hit.word_count or 0)
            if wc > 0:
                book.word_count = wc
        except (TypeError, ValueError):
            pass
    # 分类写成「书源-站内分类」；刮削成功后 TXT 归位到 novels/<书源>/<分类>/
    raw_cat = (getattr(hit, "category", "") or "").strip()
    if not raw_cat and payload.hint_category:
        raw_cat = (payload.hint_category or "").strip()
    if raw_cat:
        # 先按刮削源规范化，再拼「书源-栏目」，避免纵横旧栏目/细分名写歪
        src_n, cat_n = map_site_category(label, raw_cat[:50])
        # 纵横：映射不到一级栏目时回退搜索 catePName
        if label == "纵横" and cat_n in ("", UNCATEGORIZED, raw_cat):
            alt = payload.hint_category or ""
            if alt and alt != raw_cat:
                src_n, cat_n = map_site_category(label, alt[:50])
        book.category = make_category_label(src_n or label, cat_n)
    elif not book.category:
        book.category = UNCATEGORIZED

    # 标签：以详情 all-label 为准整体替换，避免残留旧的错误标签
    from ..scrapers.qidian import clean_tag_token, download_cover

    # 标签：详情优先，否则用搜索 hint
    raw_tags = list(hit.tags or []) or list(payload.hint_tags or [])
    cleaned = []
    for t in raw_tags:
        tok = clean_tag_token(t)
        if tok and tok not in cleaned and tok != label and tok != UNCATEGORIZED:
            cleaned.append(tok)
    # 已正式分类则去掉「未分类」标记
    book.tags = ensure_category_tag(",".join(cleaned[:12]), book.category)

    book.source = label
    book.source_id = hit.source_id or payload.source_book_id

    # 不在此处移动 TXT；仅「体检 → 按分类归位」触发 relocate

    if payload.with_cover and hit.cover_url:
        try:
            if book.cover_file:
                old = settings.covers_dir / book.cover_file
                if old.is_file():
                    old.unlink()
            settings.covers_dir.mkdir(parents=True, exist_ok=True)
            tmp = settings.covers_dir / f"{book.id}_scrape_{int(time.time())}"
            ext = download_cover(hit.cover_url, tmp)
            final = settings.covers_dir / f"{book.id}_scrape_{int(time.time())}{ext}"
            tmp.replace(final)
            book.cover_file = final.name
        except ScrapeError:
            pass

    book.updated_at = datetime.now().isoformat(timespec="seconds")
    db.commit()
    db.refresh(book)
    data = admin_book_detail(book)
    data["scrape"] = hit.to_dict()
    data["scrape_detail_error"] = detail_err
    data["source"] = book.source
    data["source_id"] = book.source_id
    return data


@router.get("/sources")
def scrape_sources() -> dict:
    return {
        "items": [
            {"key": "qidian", "label": "起点", "enabled": True},
            {"key": "fanqie", "label": "番茄", "enabled": True},
            {"key": "zongheng", "label": "纵横", "enabled": True},
        ]
    }
