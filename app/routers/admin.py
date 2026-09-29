"""管理后台 API：列表/编辑/封面上传/删除/导入。全部经会话鉴权。"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..book_query import build_books_stmt, count_books
from ..config import (
    CATEGORIES,
    UNCATEGORIZED,
    category_tree,
    make_category_label,
    map_site_category,
    normalize_source,
    safe_delete_cover,
    settings,
)
from ..database import delete_books_safe, get_db
from ..importer import get_import_status, import_all_async, request_import_cancel
from ..models import Book
from ..serializers import admin_book_detail, book_list_item, resolve_base_url

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_dep)])

ALLOWED_COVER_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# 封面上传上限：个人库封面不需要很大
MAX_COVER_BYTES = 5 * 1024 * 1024


def _detect_image_ext(data: bytes) -> str | None:
    """按魔数识别图片类型，防止改扩展名伪造上传。"""
    if not data:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=100)
    # 两级分类：category_source（本地/起点/番茄）+ category（站内栏目）
    # 兼容旧接口：也可只传合成串 category（如「起点-都市」）
    category: str | None = Field(default=None, max_length=50)
    category_source: str | None = Field(default=None, max_length=20)
    category_name: str | None = Field(default=None, max_length=50)
    intro: str | None = None
    status: str | None = Field(default=None, pattern=r"^(连载|完结|未知)$")
    tags: str | None = Field(default=None, max_length=300)
    source: str | None = Field(default=None, max_length=20)
    source_id: str | None = Field(default=None, max_length=64)


@router.get("/tags")
def admin_tags(db: Session = Depends(get_db)) -> dict:
    """标签云（C3）：用于筛选。"""
    from collections import Counter

    rows = db.execute(select(Book.tags)).scalars().all()
    counter: Counter[str] = Counter()
    for raw in rows:
        for t in (raw or "").split(","):
            t = t.strip()
            if t:
                counter[t] += 1
    items = [{"name": k, "count": v} for k, v in counter.most_common(80)]
    return {"items": items, "total": len(counter)}


@router.get("/stats")
def admin_stats(request: Request, db: Session = Depends(get_db)) -> dict:
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
        # 编辑页两级分类树
        "category_tree": category_tree(),
        "import": get_import_status(),
        "public_base_url": resolve_base_url(request),
        # 设置页展示运行环境用
        "novels_dir": str(settings.novels_dir),
        "database_path": str(settings.database_path),
        "covers_dir": str(settings.covers_dir),
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
            select(Book)
            .where(Book.title == title, Book.author == author)
            .order_by(Book.chapter_count.desc(), Book.word_count.desc(), Book.id)
        ).scalars().all()
        items.append({
            "title": title,
            "author": author,
            "count": n,
            # 与 library.report 一致：默认保留章节最多的那本
            "keep_id": books[0].id if books else 0,
            "books": [
                {
                    "id": b.id,
                    "source_path": b.source_path,
                    "source": b.source,
                    "source_id": b.source_id,
                    "chapter_count": b.chapter_count,
                    "word_count": b.word_count,
                    "cover_file": b.cover_file,
                }
                for b in books
            ],
        })
    return {"items": items, "total": len(items)}


@router.get("/books")
def admin_list_books(
    request: Request,
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    scraped: str | None = Query(default=None),  # unscraped=仅未刮削
    sort: str = Query(default="updated"),  # updated|title|author|words|chapters
    page: int = Query(default=1, ge=1),
    # 上限放宽到 200：宽屏多列时前端会请求 cols*rows，保证非末页行占满
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    base = resolve_base_url(request)
    offset = (page - 1) * page_size
    # 与公开 API 共用查询构造；管理端搜索不含简介
    stmt = build_books_stmt(
        db,
        category=category,
        q=q,
        status=status,
        tag=tag,
        source=source,
        scraped=scraped,
        sort=sort,
        with_intro_search=False,
    )
    total = count_books(db, stmt)
    books = db.execute(
        stmt.offset(offset).limit(page_size)
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [book_list_item(b, base) for b in books],
    }


@router.get("/books/{book_id}")
def admin_get_book(request: Request, book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return admin_book_detail(book, resolve_base_url(request))


@router.patch("/books/{book_id}")
def admin_update_book(
    request: Request, book_id: int, payload: BookUpdate, db: Session = Depends(get_db)
) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    data = payload.model_dump(exclude_none=True)
    if "tags" in data and data["tags"] is not None:
        tags = re.split(r"[,，;；\s]+", data["tags"].strip())
        data["tags"] = ",".join(dict.fromkeys(t for t in tags if t))
    if "source_id" in data and data["source_id"] is not None:
        data["source_id"] = data["source_id"].strip()
    if "title" in data and not data["title"].strip():
        raise HTTPException(400, "书名不能为空")
    # 两级分类写入：优先 category_source + category_name，兼容合成串 category
    cat_src = (data.pop("category_source", None) if "category_source" in data else None)
    cat_name = (data.pop("category_name", None) if "category_name" in data else None)
    if cat_src is not None or cat_name is not None or ("category" in data and data["category"] is not None):
        if cat_name is not None or cat_src is not None:
            src_n, name_n = map_site_category(cat_src or "", cat_name or data.get("category") or "")
            if not name_n:
                name_n = UNCATEGORIZED
            data["category"] = make_category_label(src_n, name_n)
            # 站源与分类书源对齐（有刮削源时保留 source_id）
            if src_n:
                data["source"] = src_n
        else:
            raw_cat = (data["category"] or "").strip() or UNCATEGORIZED
            src_n, name_n = map_site_category("", raw_cat)
            data["category"] = make_category_label(src_n, name_n)
            if src_n and "source" not in data:
                data["source"] = src_n
        # 刮掉中间字段，避免 setattr 失败
        data.pop("category_name", None)
        data.pop("category_source", None)
    if "source" in data and data["source"] is not None:
        data["source"] = normalize_source(data["source"].strip()) or data["source"].strip()
    for k, v in data.items():
        setattr(book, k, v)
    # 不在保存时移动 TXT；仅「体检 → 按分类归位」触发 relocate
    # 元数据变更后刷新更新时间，保证「导入/更新」排序准确
    book.updated_at = datetime.now().isoformat(timespec="seconds")
    db.commit()
    db.refresh(book)
    return admin_book_detail(book, resolve_base_url(request))


@router.post("/books/{book_id}/cover")
def admin_upload_cover(
    request: Request,
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
    raw = file.file.read()
    if not raw:
        raise HTTPException(400, "封面文件为空")
    if len(raw) > MAX_COVER_BYTES:
        raise HTTPException(400, f"封面过大，请控制在 {MAX_COVER_BYTES // (1024 * 1024)}MB 以内")
    # 以文件魔数为准，扩展名伪造会被拒绝
    magic_ext = _detect_image_ext(raw)
    if magic_ext is None:
        raise HTTPException(400, "不是有效的图片文件（支持 jpg / png / webp / gif）")
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    # 删除旧封面（仅 covers 内图片，源 TXT 不受影响）
    if book.cover_file:
        safe_delete_cover(book.cover_file)
    # 统一用魔数识别的扩展名落盘
    new_name = f"{book.id}_{int(time.time())}{magic_ext}"
    dest = settings.covers_dir / new_name
    dest.write_bytes(raw)
    book.cover_file = new_name
    db.commit()
    db.refresh(book)
    return admin_book_detail(book, resolve_base_url(request))


@router.delete("/books/{book_id}")
def admin_delete_book(book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    # 只删封面图片，绝不删除 novels/ 下源 TXT
    if book.cover_file:
        safe_delete_cover(book.cover_file)
    title = book.title
    try:
        # 批量删章节+书籍；FTS 触发器失败时自动重建索引，避免裸 500
        repaired = delete_books_safe(db, [book_id])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"删除失败：{e}") from e
    return {"ok": True, "deleted": title, "id": book_id, "fts_repaired": repaired}


class BookProgressIn(BaseModel):
    """阅读进度：百分比 0–100，可选章节序号用于续读。"""

    percent: int = Field(default=0, ge=0, le=100)
    chapter_index: int | None = Field(default=None, ge=-1)


class BatchDeleteIn(BaseModel):
    """批量删除请求体。"""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


@router.put("/books/{book_id}/progress")
def admin_update_progress(
    request: Request, book_id: int, payload: BookProgressIn, db: Session = Depends(get_db)
) -> dict:
    """写入阅读进度百分比（阅读器/列表共用）。"""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    book.read_percent = int(payload.percent)
    if payload.chapter_index is not None:
        book.read_chapter_index = int(payload.chapter_index)
    book.read_at = datetime.now().isoformat(timespec="seconds")
    db.commit()
    db.refresh(book)
    return {
        "ok": True,
        "id": book.id,
        "read_percent": book.read_percent,
        "read_chapter_index": book.read_chapter_index,
        "read_at": book.read_at,
    }


@router.post("/books/batch/delete")
def admin_batch_delete(payload: BatchDeleteIn, db: Session = Depends(get_db)) -> dict:
    """批量删除书籍（含封面与正文包），供书库多选操作。"""
    ids = sorted({int(i) for i in payload.ids if i and int(i) > 0})
    if not ids:
        raise HTTPException(400, "未选择书籍")
    titles: list[str] = []
    for bid in ids:
        book = db.get(Book, bid)
        if not book:
            continue
        titles.append(book.title)
        if book.cover_file:
            safe_delete_cover(book.cover_file)
    try:
        repaired = delete_books_safe(db, ids)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"批量删除失败：{e}") from e
    return {
        "ok": True,
        "deleted_count": len(titles),
        "deleted": titles,
        "ids": ids,
        "fts_repaired": repaired,
    }


@router.post("/import")
def admin_import(mode: str = Query(default="local", pattern="^local$")) -> dict:
    # WebDAV 导入已移除，仅支持本地 NOVELS_DIR
    started = import_all_async("local")
    return {"started": started, "mode": "local", "import": get_import_status()}


@router.post("/import/cancel")
def admin_import_cancel() -> dict:
    """请求停止导入（A6）。"""
    ok = request_import_cancel()
    return {"ok": ok, "import": get_import_status()}


@router.get("/import/status")
def admin_import_status() -> dict:
    return get_import_status()


@router.get("/import/logs")
def admin_import_logs(date: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200)) -> dict:
    """历史导入记录；date=YYYY-MM-DD 按完成日过滤。"""
    from ..importer import query_import_logs

    items = query_import_logs(date=date, limit=limit)
    return {"items": items, "total": len(items)}


def _sse_pack(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.get("/import/stream")
async def admin_import_stream(request: Request):
    """导入进度 SSE（C5）。"""
    import asyncio

    async def gen():
        for _ in range(600):
            if await request.is_disconnected():
                break
            st = get_import_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/scrape/batch/stream")
async def admin_batch_stream(request: Request):
    """批量刮削进度 SSE（C5）。"""
    import asyncio

    from ..batch_scrape import get_batch_status

    async def gen():
        for _ in range(600):
            if await request.is_disconnected():
                break
            st = get_batch_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")
