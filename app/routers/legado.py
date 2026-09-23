"""Legado（开源阅读）专用 API：返回完整 URL + 稳定 JSON 结构，方便 JsonPath 解析。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, Chapter
from ..serializers import resolve_base_url

router = APIRouter(prefix="/api/legado", tags=["legado"])


def _abs(path: str, base: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _explore_item(book: Book, base: str) -> dict:
    return {
        "name": book.title,
        "author": book.author,
        "cover_url": _abs(f"/covers/{book.cover_file}", base) if book.cover_file else "",
        "intro": (book.intro or "")[:200],
        "kind": ",".join([book.category, *book.tags_list, book.status]),
        "lastChapter": book.latest_chapter,
        "detail_url": _abs(f"/api/legado/book/{book.id}", base),
        "book_url": _abs(f"/api/legado/book/{book.id}", base),
        "toc_url": _abs(f"/api/legado/toc/{book.id}", base),
        "word_count": book.word_count,
        "category": book.category,
        "status": book.status,
    }


@router.get("/categories")
def legado_categories(request: Request, db: Session = Depends(get_db)) -> dict:
    base = resolve_base_url(request)
    rows = db.execute(select(Book.category, func.count(Book.id)).group_by(Book.category)).all()
    return {
        "categories": [
            {
                "name": c,
                "count": n,
                "explore_url": _abs(f"/api/legado/explore/{c}", base),
            }
            for c, n in rows
        ]
    }


@router.get("/explore/{category}")
def legado_explore(
    request: Request,
    category: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    base = resolve_base_url(request)
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
        "books": [_explore_item(b, base) for b in books],
    }


@router.get("/search")
def legado_search(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    base = resolve_base_url(request)
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
        "books": [_explore_item(b, base) for b in books],
    }


@router.get("/book/{book_id}")
def legado_book(request: Request, book_id: int, db: Session = Depends(get_db)) -> dict:
    base = resolve_base_url(request)
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return {
        "name": book.title,
        "author": book.author,
        "cover_url": _abs(f"/covers/{book.cover_file}", base) if book.cover_file else "",
        "intro": book.intro or "",
        "kind": ",".join([book.category, *book.tags_list, book.status]),
        "lastChapter": book.latest_chapter,
        "toc_url": _abs(f"/api/legado/toc/{book.id}", base),
        "detail_url": _abs(f"/api/legado/book/{book.id}", base),
        "category": book.category,
        "status": book.status,
        "word_count": book.word_count,
        "chapter_count": book.chapter_count,
        "book": {
            "id": book.id,
            "name": book.title,
            "author": book.author,
            "cover_url": _abs(f"/covers/{book.cover_file}", base) if book.cover_file else "",
            "intro": book.intro or "",
            "tags": book.tags_list,
            "status": book.status,
            "toc_url": _abs(f"/api/legado/toc/{book.id}", base),
        },
    }


@router.get("/toc/{book_id}")
def legado_toc(request: Request, book_id: int, db: Session = Depends(get_db)) -> dict:
    base = resolve_base_url(request)
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    chapters = db.execute(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.index)
    ).scalars().all()
    return {
        "name": book.title,
        "total": len(chapters),
        "toc_url": _abs(f"/api/legado/toc/{book.id}", base),
        "chapters": [
            {
                "name": c.title,
                "title": c.title,
                "index": c.index,
                "content_url": _abs(f"/api/legado/content/{book_id}/{c.id}", base),
                "url": _abs(f"/api/legado/content/{book_id}/{c.id}", base),
            }
            for c in chapters
        ],
    }


@router.get("/content/{book_id}/{chapter_id}")
def legado_content(
    request: Request, book_id: int, chapter_id: int, db: Session = Depends(get_db)
) -> dict:
    base = resolve_base_url(request)
    ch = db.get(Chapter, chapter_id)
    if not ch or ch.book_id != book_id:
        raise HTTPException(404, "章节不存在")
    return {
        "title": ch.title,
        "content": ch.content,
        "content_url": _abs(f"/api/legado/content/{book_id}/{chapter_id}", base),
        "isVip": False,
        "isPay": False,
    }


@router.get("/book-source")
def legado_book_source(request: Request) -> list:
    """返回注入了当前访问基址的 Legado 书源配置（数组，可直接导入）。"""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "legado_book_source.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Legado 导入要求根节点为数组；兼容历史单对象文件
    sources = data if isinstance(data, list) else [data]
    base = resolve_base_url(request)
    for item in sources:
        if not isinstance(item, dict):
            continue
        item["bookSourceUrl"] = base
        item["bookSourceName"] = item.get("bookSourceName") or "爱小说"
        item["bookSourceGroup"] = item.get("bookSourceGroup") or "本地NAS"
    return sources
