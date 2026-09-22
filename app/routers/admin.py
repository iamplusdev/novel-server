"""管理后台 API：列表/编辑/封面上传/删除/导入。全部经会话鉴权。"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..config import CATEGORIES, settings
from ..database import get_db
from ..importer import get_import_status, import_all_async
from ..models import Book
from ..serializers import admin_book_detail, book_list_item

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_dep)])

ALLOWED_COVER_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    intro: str | None = None
    status: str | None = Field(default=None, pattern=r"^(连载|完结|未知)$")
    tags: str | None = Field(default=None, max_length=300)
    source: str | None = Field(default=None, max_length=20)
    source_id: str | None = Field(default=None, max_length=64)


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)) -> dict:
    total_books = db.execute(select(func.count(Book.id))).scalar_one()
    total_words = db.execute(select(func.coalesce(func.sum(Book.word_count), 0))).scalar_one()
    by_cat = db.execute(select(Book.category, func.count(Book.id)).group_by(Book.category)).all()
    by_status = db.execute(select(Book.status, func.count(Book.id)).group_by(Book.status)).all()
    return {
        "total_books": total_books,
        "total_words": total_words,
        "by_category": [{"name": c, "count": n} for c, n in by_cat],
        "by_status": [{"name": s, "count": n} for s, n in by_status],
        "categories": CATEGORIES,
        "import": get_import_status(),
        "public_base_url": settings.public_base_url,
    }


@router.get("/duplicates")
def admin_duplicates(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Book.title, Book.author, func.count(Book.id).label("n"))
        .group_by(Book.title, Book.author)
        .having(func.count(Book.id) > 1)
    ).all()
    items = []
    for title, author, n in rows:
        books = db.execute(
            select(Book).where(Book.title == title, Book.author == author).order_by(Book.id)
        ).scalars().all()
        items.append({
            "title": title,
            "author": author,
            "count": n,
            "books": [
                {"id": b.id, "source_path": b.source_path, "source": b.source, "source_id": b.source_id, "chapter_count": b.chapter_count}
                for b in books
            ],
        })
    return {"items": items, "total": len(items)}
    total_books = db.execute(select(func.count(Book.id))).scalar_one()
    total_words = db.execute(select(func.coalesce(func.sum(Book.word_count), 0))).scalar_one()
    by_cat = db.execute(select(Book.category, func.count(Book.id)).group_by(Book.category)).all()
    by_status = db.execute(select(Book.status, func.count(Book.id)).group_by(Book.status)).all()
    return {
        "total_books": total_books,
        "total_words": total_words,
        "by_category": [{"name": c, "count": n} for c, n in by_cat],
        "by_status": [{"name": s, "count": n} for s, n in by_status],
        "categories": CATEGORIES,
        "import": get_import_status(),
        "public_base_url": settings.public_base_url,
    }


@router.get("/books")
def admin_list_books(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="updated"),  # updated|title|author|words|chapters
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    offset = (page - 1) * page_size
    stmt = select(Book)
    if category:
        stmt = stmt.where(Book.category == category)
    if status:
        stmt = stmt.where(Book.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Book.title.like(like), Book.author.like(like), Book.tags.like(like))
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    if sort == "title":
        order = (Book.title.asc(), Book.id.asc())
    elif sort == "author":
        order = (Book.author.asc(), Book.title.asc())
    elif sort == "words":
        order = (Book.word_count.desc(), Book.title.asc())
    elif sort == "chapters":
        order = (Book.chapter_count.desc(), Book.title.asc())
    else:
        order = (Book.updated_at.desc(), Book.id.desc())
    books = db.execute(
        stmt.order_by(*order).offset(offset).limit(page_size)
    ).scalars().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [book_list_item(b) for b in books]}


@router.get("/books/{book_id}")
def admin_get_book(book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return admin_book_detail(book)


@router.patch("/books/{book_id}")
def admin_update_book(book_id: int, payload: BookUpdate, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    data = payload.model_dump(exclude_none=True)
    if "tags" in data and data["tags"] is not None:
        tags = re.split(r"[,，;；\s]+", data["tags"].strip())
        data["tags"] = ",".join(dict.fromkeys(t for t in tags if t))
    if "source" in data and data["source"] is not None:
        data["source"] = data["source"].strip()
    if "source_id" in data and data["source_id"] is not None:
        data["source_id"] = data["source_id"].strip()
    if "title" in data and not data["title"].strip():
        raise HTTPException(400, "书名不能为空")
    for k, v in data.items():
        setattr(book, k, v)
    db.commit()
    db.refresh(book)
    return admin_book_detail(book)


@router.post("/books/{book_id}/cover")
def admin_upload_cover(
    book_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    filename = file.filename or "cover"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_COVER_EXT:
        raise HTTPException(400, f"不支持的封面格式，请使用 {', '.join(sorted(ALLOWED_COVER_EXT))}")
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    # 删除旧封面
    if book.cover_file:
        old = settings.covers_dir / book.cover_file
        if old.is_file():
            try:
                old.unlink()
            except OSError:
                pass
    new_name = f"{book.id}_{int(time.time())}{ext}"
    dest = settings.covers_dir / new_name
    dest.write_bytes(file.file.read())
    book.cover_file = new_name
    db.commit()
    db.refresh(book)
    return admin_book_detail(book)


@router.delete("/books/{book_id}")
def admin_delete_book(book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    if book.cover_file:
        cover = settings.covers_dir / book.cover_file
        if cover.is_file():
            try:
                cover.unlink()
            except OSError:
                pass
    title = book.title
    db.delete(book)
    db.commit()
    return {"ok": True, "deleted": title, "id": book_id}


@router.post("/import")
def admin_import() -> dict:
    started = import_all_async()
    return {"started": started, "import": get_import_status()}


@router.get("/import/status")
def admin_import_status() -> dict:
    return get_import_status()



