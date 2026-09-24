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
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..config import (
    CATEGORIES,
    UNCATEGORIZED,
    category_tree,
    make_category_label,
    map_site_category,
    normalize_source,
    parse_category_label,
    safe_delete_cover,
    settings,
)
from ..database import delete_books_safe, escape_like, fts_available, get_db
from ..importer import get_import_status, import_all_async, relocate_local_txt, request_import_cancel
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


@router.get("/books")
def admin_list_books(
    request: Request,
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str = Query(default="updated"),  # updated|title|author|words|chapters
    page: int = Query(default=1, ge=1),
    # 上限放宽到 200：宽屏多列时前端会请求 cols*rows，保证非末页行占满
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    base = resolve_base_url(request)
    offset = (page - 1) * page_size
    stmt = select(Book)
    # 书源 + 分类：支持「起点」「都市」「起点-都市」等组合（统一归一化）
    src_raw = (source or "").strip()
    cat_raw = (category or "").strip()
    if cat_raw:
        psrc, pure = parse_category_label(cat_raw)
        if psrc:
            src_raw = src_raw or psrc
            cat_raw = pure or cat_raw
        else:
            cat_raw = pure or cat_raw
    if src_raw in ("本地", "none", "-"):
        src_raw = ""
        local_only = True
    else:
        local_only = False
    if local_only:
        stmt = stmt.where(
            ~Book.category.like("起点-%", escape="\\"),
            ~Book.category.like("番茄-%", escape="\\"),
        )
    elif src_raw in ("起点", "番茄"):
        # 有书源时：合成串前缀 或 source 字段
        stmt = stmt.where(
            or_(
                Book.category.startswith(f"{src_raw}-"),
                Book.source == src_raw,
            )
        )
    if cat_raw and cat_raw != "全部":
        if src_raw in ("起点", "番茄"):
            # 书源+分类：优先整标签，再纯名 / 后缀
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
                or_(
                    Book.category == cat_raw,
                    Book.category.endswith(f"-{cat_raw}"),
                )
            )
    if status:
        stmt = stmt.where(Book.status == status)
    # 标签筛选（保留 API，界面已隐藏）
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
        # 与公开搜索一致：FTS 优先（A9）
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
                like = f"%{escape_like(q)}%"
                stmt = stmt.where(
                    or_(
                        Book.title.like(like, escape="\\"),
                        Book.author.like(like, escape="\\"),
                        Book.tags.like(like, escape="\\"),
                    )
                )
        else:
            like = f"%{escape_like(q)}%"
            stmt = stmt.where(
                or_(
                    Book.title.like(like, escape="\\"),
                    Book.author.like(like, escape="\\"),
                    Book.tags.like(like, escape="\\"),
                )
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
    # 分类变更后本地 TXT 归位到 novels/<书源>/<分类>/
    if "category" in data:
        relocate_local_txt(book)
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


def _sse_pack(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.get("/import/stream")
def admin_import_stream():
    """导入进度 SSE（C5）：每 1s 推送状态，结束后关闭。"""
    import asyncio

    async def gen():
        # 最多推送 10 分钟，防止挂死连接
        for _ in range(600):
            st = get_import_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/scrape/batch/stream")
def admin_batch_stream():
    """批量刮削进度 SSE（C5）。"""
    import asyncio

    from ..batch_scrape import get_batch_status

    async def gen():
        for _ in range(600):
            st = get_batch_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")
