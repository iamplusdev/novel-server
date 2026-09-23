"""刮削 API：搜索站外元数据并写回本地书籍。"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..config import UNCATEGORIZED, make_category_label, map_site_category, normalize_source, settings
from ..database import get_db
from ..importer import ensure_category_tag, relocate_local_txt
from ..models import Book
from ..scrapers import REGISTRY, SOURCE_LABELS
from ..scrapers.qidian import ScrapeError, download_cover
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


class ApplyIn(BaseModel):
    source: str = Field(default="qidian", max_length=20)
    source_book_id: str = Field(..., min_length=1, max_length=32)
    keyword: str | None = Field(default=None, max_length=80)
    with_cover: bool = True
    # 搜索列表里已有的字段，详情被风控时可作回退
    hint_name: str | None = Field(default=None, max_length=200)
    hint_author: str | None = Field(default=None, max_length=100)
    hint_intro: str | None = Field(default=None, max_length=1000)
    hint_status: str | None = Field(default=None, max_length=20)
    hint_cover_url: str | None = Field(default=None, max_length=500)
    hint_tags: list[str] | None = None
    hint_word_count: int = Field(default=0, ge=0)


def _mod(source: str):
    mod = REGISTRY.get((source or "").strip().lower()) or REGISTRY.get((source or "").strip())
    if not mod:
        raise HTTPException(400, f"暂不支持的刮削源: {source}")
    return mod


@router.post("/search")
def scrape_search(payload: SearchIn) -> dict:
    mod = _mod(payload.source)
    try:
        hits = mod.search(payload.keyword, limit=payload.limit)
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e
    label = SOURCE_LABELS.get(payload.source.strip().lower(), payload.source)
    return {
        "source": label,
        "source_key": payload.source,
        "query": payload.keyword,
        "items": [h.to_dict() for h in hits],
        "count": len(hits),
    }


@router.post("/detail")
def scrape_detail(payload: ApplyIn) -> dict:
    mod = _mod(payload.source)
    raw = (payload.source_book_id or "").strip()
    extract = getattr(mod, "extract_book_id", None)
    bid = (extract(raw) if extract else raw) or raw
    try:
        hit = mod.fetch_detail(bid)
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e
    return hit.to_dict()


@router.post("/books/{book_id}/apply")
def scrape_apply(book_id: int, payload: ApplyIn, db: Session = Depends(get_db)) -> dict:
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
        hit = mod.fetch_detail(payload.source_book_id)
    except ScrapeError as e:
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

    # 合并 hint
    if not hit.name and payload.hint_name:
        hit.name = payload.hint_name
    if not hit.author and payload.hint_author:
        hit.author = payload.hint_author
    if not hit.intro and payload.hint_intro:
        hit.intro = payload.hint_intro
    if not hit.status and payload.hint_status:
        s = (payload.hint_status or "").strip()
        hit.status = "完结" if s in ("完结", "已完结", "完本") else ("连载" if s.startswith("连载") else s)
    if not hit.cover_url and payload.hint_cover_url:
        hit.cover_url = payload.hint_cover_url
    if not getattr(hit, "word_count", 0) and payload.hint_word_count:
        hit.word_count = int(payload.hint_word_count or 0)

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
    if getattr(hit, "category", ""):
        raw_cat = (hit.category or "").strip()[:50]
        book.category = category_label_from_hit(label, raw_cat)
    elif not book.category:
        book.category = UNCATEGORIZED

    # 标签：以详情 all-label 为准整体替换，避免残留旧的错误标签
    from ..scrapers.qidian import clean_tag_token

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

    # 本地 TXT 移到 novels/<书源>/<分类>/（WebDAV 路径跳过）
    relocate_local_txt(book)

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
        ]
    }
