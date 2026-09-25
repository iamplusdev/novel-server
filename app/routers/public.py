"""公开 JSON API：分类、列表、搜索、详情、目录、正文。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..book_query import build_books_stmt, count_books
from ..config import all_category_labels
from ..database import get_db
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
    # 固定分类（书源两级）+ 实际出现的其它分类
    seen = set()
    for name in all_category_labels():
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
    tag: str | None = None,
    source: str | None = None,
    sort: str = "updated",
    page: int = 1,
    page_size: int = 20,
    base: str | None = None,
) -> dict:
    offset, limit = _paginate(page, page_size)
    # 公开搜索带简介；筛选/排序统一走 book_query
    stmt = build_books_stmt(
        db,
        category=category,
        q=q,
        status=status,
        tag=tag,
        source=source,
        sort=sort,
        with_intro_search=True,
    )
    total = count_books(db, stmt)
    books = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": limit,
        "items": [book_list_item(b, base) for b in books],
    }


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)) -> dict:
    """公开标签云（C3），阅读器筛选用。"""
    from collections import Counter

    rows = db.execute(select(Book.tags)).scalars().all()
    counter: Counter[str] = Counter()
    for raw in rows:
        for t in (raw or "").split(","):
            t = t.strip()
            if t:
                counter[t] += 1
    return {
        "items": [{"name": k, "count": v} for k, v in counter.most_common(80)],
        "total": len(counter),
    }


@router.get("/books")
def list_books(
    request: Request,
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str = Query(default="updated"),  # updated | title | author
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return _query_books(
        db,
        category=category,
        source=source,
        q=q,
        status=status,
        tag=tag,
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
    # 目录只取标题列，避免整本正文进内存
    chapters = db.execute(
        select(Chapter.id, Chapter.book_id, Chapter.index, Chapter.title)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.index)
        .offset(offset)
        .limit(limit)
    ).all()
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
