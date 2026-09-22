"""刮削 API：搜索站外元数据并写回本地书籍。"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..config import settings
from ..database import get_db
from ..models import Book
from ..scrapers import REGISTRY, SOURCE_LABELS
from ..scrapers.qidian import ScrapeError, download_cover
from ..serializers import admin_book_detail

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
    try:
        hit = mod.fetch_detail(payload.source_book_id)
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e
    return hit.to_dict()


@router.post("/books/{book_id}/apply")
def scrape_apply(book_id: int, payload: ApplyIn, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    mod = _mod(payload.source)
    label = SOURCE_LABELS.get(payload.source.strip().lower(), "起点")

    sid = (payload.source_book_id or "").strip()
    taken = db.execute(
        select(Book).where(Book.source_id == sid, Book.source == label, Book.id != book_id)
    ).scalars().first()
    if taken:
        raise HTTPException(
            409,
            f"起点 ID {sid} 已绑定到《{taken.title}》(ID {taken.id})，请勿重复刮削到多本书",
        )

    hit = None
    detail_err = ""
    try:
        hit = mod.fetch_detail(payload.source_book_id)
    except ScrapeError as e:
        detail_err = str(e)
        from ..scrapers.qidian import ScrapeHit as QdHit

        hit = QdHit(
            source_id=payload.source_book_id,
            url=f"https://www.qidian.com/book/{payload.source_book_id}/",
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
    if getattr(hit, "category", ""):
        book.category = hit.category[:50]

    # 标签：以详情 all-label 为准整体替换，避免残留旧的错误标签
    from ..scrapers.qidian import clean_tag_token

    raw_tags = list(hit.tags or []) or list(payload.hint_tags or [])
    cleaned = []
    for t in raw_tags:
        tok = clean_tag_token(t)
        if tok and tok not in cleaned and tok != label:
            cleaned.append(tok)
    book.tags = ",".join(cleaned[:12])

    book.source = label
    book.source_id = hit.source_id or payload.source_book_id

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

    book.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
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
            {"key": "fanqie", "label": "番茄小说", "enabled": False},
        ]
    }
