"""公开 JSON API：分类、列表、搜索、详情、目录、正文。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import CATEGORIES, all_category_labels
from ..database import escape_like, fts_available, get_db
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
    stmt = select(Book)
    src_raw = (source or "").strip()
    cat_raw = (category or "").strip()
    if cat_raw:
        from ..config import parse_category_label

        psrc, pure = parse_category_label(cat_raw)
        if psrc:
            src_raw = src_raw or psrc
            cat_raw = pure or cat_raw
        else:
            cat_raw = pure or cat_raw
    if src_raw in ("本地", "none", "-"):
        src_raw = ""
        stmt = stmt.where(
            ~Book.category.like("起点-%", escape="\\"),
            ~Book.category.like("番茄-%", escape="\\"),
        )
    elif src_raw in ("起点", "番茄"):
        stmt = stmt.where(
            or_(Book.category.startswith(f"{src_raw}-"), Book.source == src_raw)
        )
    if cat_raw and cat_raw != "全部":
        from sqlalchemy import and_

        if src_raw in ("起点", "番茄"):
            label = f"{src_raw}-{cat_raw}"
            stmt = stmt.where(
                or_(
                    Book.category == label,
                    Book.category == cat_raw,
                    and_(
                        Book.category.startswith(f"{src_raw}-"),
                        Book.category.endswith(f"-{cat_raw}"),
                    ),
                    and_(Book.source == src_raw, Book.category == cat_raw),
                )
            )
        else:
            stmt = stmt.where(
                or_(Book.category == cat_raw, Book.category.endswith(f"-{cat_raw}"))
            )
    if status:
        stmt = stmt.where(Book.status == status)
    if tag:
        tag = tag.strip()
        stmt = stmt.where(
            or_(
                Book.tags == tag,
                Book.tags.like(f"{tag},%", escape="\\"),
                Book.tags.like(f"%,{tag}", escape="\\"),
                Book.tags.like(f"%,{tag},%", escape="\\"),
            )
        )
    if q:
        q = q.strip()
        # 优先 FTS5（A9），失败或无索引则退回 LIKE
        if fts_available():
            from sqlalchemy import text as sa_text

            fts_ids = [
                r[0]
                for r in db.execute(
                    sa_text("SELECT rowid FROM books_fts WHERE books_fts MATCH :q"),
                    {"q": q.replace('"', " ")},
                ).all()
            ]
            if fts_ids:
                stmt = stmt.where(Book.id.in_(fts_ids))
            else:
                # FTS 无命中时也做 LIKE 兜底（拼音/部分词）
                like = f"%{escape_like(q)}%"
                stmt = stmt.where(
                    or_(
                        Book.title.like(like, escape="\\"),
                        Book.author.like(like, escape="\\"),
                        Book.tags.like(like, escape="\\"),
                        Book.intro.like(like, escape="\\"),
                    )
                )
        else:
            like = f"%{escape_like(q)}%"
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
