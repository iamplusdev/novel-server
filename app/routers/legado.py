"""Legado（开源阅读）专用 API：返回完整 URL + 稳定 JSON 结构，方便 JsonPath 解析。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Book, Chapter

router = APIRouter(prefix="/api/legado", tags=["legado"])


def _abs(path: str) -> str:
    return f"{settings.public_base_url}{path}"


def _explore_item(book: Book) -> dict:
    return {
        "name": book.title,
        "author": book.author,
        "cover_url": _abs(f"/covers/{book.cover_file}") if book.cover_file else "",
        "intro": (book.intro or "")[:200],
        "kind": ",".join([book.category, *book.tags_list, book.status]),
        "lastChapter": book.latest_chapter,
        "detail_url": _abs(f"/api/legado/book/{book.id}"),
        "book_url": _abs(f"/api/legado/book/{book.id}"),
        "toc_url": _abs(f"/api/legado/toc/{book.id}"),
        "word_count": book.word_count,
        "category": book.category,
        "status": book.status,
    }


@router.get("/categories")
def legado_categories(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Book.category, func.count(Book.id)).group_by(Book.category)).all()
    return {
        "categories": [
            {
                "name": c,
                "count": n,
                "explore_url": _abs(f"/api/legado/explore/{c}"),
            }
            for c, n in rows
        ]
    }


@router.get("/explore/{category}")
def legado_explore(
    category: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    page_size = min(max(1, page_size), 50)
    offset = (page - 1) * page_size
    total = db.execute(
        select(func.count()).select_from(Book).where(Book.category == category)
    ).scalar_one()
    books = db.execute(
        select(Book)
        .where(Book.category == category)
        .order_by(Book.updated_at.desc(), Book.id.desc())
        .offset(offset)
        .limit(page_size)
    ).scalars().all()
    return {
        "name": category,
        "page": page,
        "total": total,
        "has_more": offset + len(books) < total,
        "books": [_explore_item(b) for b in books],
    }


@router.get("/search")
def legado_search(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    page_size = min(max(1, page_size), 50)
    offset = (page - 1) * page_size
    like = f"%{q.strip()}%"
    stmt = select(Book).where(
        or_(Book.title.like(like), Book.author.like(like), Book.tags.like(like))
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    books = db.execute(
        stmt.order_by(Book.title).offset(offset).limit(page_size)
    ).scalars().all()
    return {
        "q": q,
        "page": page,
        "total": total,
        "has_more": offset + len(books) < total,
        "books": [_explore_item(b) for b in books],
    }


@router.get("/book/{book_id}")
def legado_book(book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return {
        "name": book.title,
        "author": book.author,
        "cover_url": _abs(f"/covers/{book.cover_file}") if book.cover_file else "",
        "intro": book.intro or "",
        "kind": ",".join([book.category, *book.tags_list, book.status]),
        "lastChapter": book.latest_chapter,
        "toc_url": _abs(f"/api/legado/toc/{book.id}"),
        "detail_url": _abs(f"/api/legado/book/{book.id}"),
        "category": book.category,
        "status": book.status,
        "word_count": book.word_count,
        "chapter_count": book.chapter_count,
        "book": {
            "id": book.id,
            "name": book.title,
            "author": book.author,
            "cover_url": _abs(f"/covers/{book.cover_file}") if book.cover_file else "",
            "intro": book.intro or "",
            "tags": book.tags_list,
            "status": book.status,
            "toc_url": _abs(f"/api/legado/toc/{book.id}"),
        },
    }


@router.get("/toc/{book_id}")
def legado_toc(book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    chapters = db.execute(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.index)
    ).scalars().all()
    return {
        "name": book.title,
        "total": len(chapters),
        "toc_url": _abs(f"/api/legado/toc/{book.id}"),
        "chapters": [
            {
                "name": c.title,
                "title": c.title,
                "index": c.index,
                "content_url": _abs(f"/api/legado/content/{book_id}/{c.id}"),
                "url": _abs(f"/api/legado/content/{book_id}/{c.id}"),
            }
            for c in chapters
        ],
    }


@router.get("/content/{book_id}/{chapter_id}")
def legado_content(book_id: int, chapter_id: int, db: Session = Depends(get_db)) -> dict:
    ch = db.get(Chapter, chapter_id)
    if not ch or ch.book_id != book_id:
        raise HTTPException(404, "章节不存在")
    return {
        "title": ch.title,
        "content": ch.content,
        "content_url": _abs(f"/api/legado/content/{book_id}/{chapter_id}"),
        "isVip": False,
        "isPay": False,
    }


@router.get("/book-source")
def legado_book_source() -> dict:
    """返回注入了当前 PUBLIC_BASE_URL 的 Legado 书源配置。"""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "legado_book_source.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["bookSourceUrl"] = settings.public_base_url
    data["bookSourceName"] = data.get("bookSourceName") or "爱小说"
    data["bookSourceGroup"] = data.get("bookSourceGroup") or "本地NAS"
    return data
