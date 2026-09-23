"""公开 JSON API：分类、列表、搜索、详情、目录、正文。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import CATEGORIES
from ..database import escape_like, get_db
from ..models import Book, Chapter
from ..serializers import (
    book_detail,
    book_list_item,
    chapter_content,
    chapter_item,
    resolve_base_url,
)

router = APIRouter(prefix="/api", tags=["public"])


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return (page - 1) * page_size, page_size


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Book.category, func.count(Book.id)).group_by(Book.category)
    ).all()
    counts = {c: n for c, n in rows}
    items = []
    # 固定分类 + 实际出现的其它分类
    seen = set()
    for name in CATEGORIES:
        seen.add(name)
        items.append({"name": name, "count": counts.get(name, 0)})
    for name, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if name not in seen:
            items.append({"name": name, "count": n})
    return {"categories": items, "total_books": sum(counts.values())}


def _query_books(
    db: Session,
    *,
    category: str | None = None,
    q: str | None = None,
    status: str | None = None,
    sort: str = "updated",
    page: int = 1,
    page_size: int = 20,
    base: str | None = None,
) -> dict:
    offset, limit = _paginate(page, page_size)
    stmt = select(Book)
    if category:
        stmt = stmt.where(Book.category == category)
    if status:
        stmt = stmt.where(Book.status == status)
    if q:
        like = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                Book.title.like(like, escape="\\"),
                Book.author.like(like, escape="\\"),
                Book.tags.like(like, escape="\\"),
                Book.intro.like(like, escape="\\"),
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    if sort == "title":
        stmt = stmt.order_by(Book.title)
    elif sort == "author":
        stmt = stmt.order_by(Book.author, Book.title)
    elif sort == "words":
        stmt = stmt.order_by(Book.word_count.desc(), Book.title)
    elif sort == "chapters":
        stmt = stmt.order_by(Book.chapter_count.desc(), Book.title)
    else:
        stmt = stmt.order_by(Book.updated_at.desc(), Book.id.desc())

    books = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": limit,
        "items": [book_list_item(b, base) for b in books],
    }


@router.get("/books")
def list_books(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="updated"),  # updated | title | author
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return _query_books(
        db,
        category=category,
        q=q,
        status=status,
        sort=sort,
        page=page,
        page_size=page_size,
        base=resolve_base_url(request),
    )


@router.get("/search")
def search_books(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return _query_books(db, q=q, page=page, page_size=page_size, base=resolve_base_url(request))


@router.get("/books/{book_id}")
def get_book(request: Request, book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return book_detail(book, with_chapters=False, base=resolve_base_url(request))


@router.get("/books/{book_id}/chapters")
def list_chapters(
    request: Request,
    book_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    offset, limit = _paginate(page, page_size)
    total = db.execute(
        select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id)
    ).scalar_one()
    chapters = db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.index)
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return {
        "book_id": book_id,
        "book_name": book.title,
        "total": total,
        "page": page,
        "page_size": limit,
        "toc_url": f"/api/books/{book_id}/chapters",
        "items": [chapter_item(c, resolve_base_url(request)) for c in chapters],
    }


@router.get("/books/{book_id}/chapters/{chapter_id}")
def get_chapter(
    request: Request, book_id: int, chapter_id: int, db: Session = Depends(get_db)
) -> dict:
    ch = db.get(Chapter, chapter_id)
    if not ch or ch.book_id != book_id:
        raise HTTPException(404, "章节不存在")
    return chapter_content(ch, resolve_base_url(request))
