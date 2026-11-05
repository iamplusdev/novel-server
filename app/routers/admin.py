"""管理后台 API：列表/编辑/封面上传/删除/导入。全部经会话鉴权。"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .. import stats_cache
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
from ..content_store import read_book_texts
from ..database import commit_with_fts_recovery, delete_books_safe, get_db
from ..importer import (
    ensure_category_tag,
    get_import_status,
    import_all_async,
    request_import_cancel,
)
from ..models import Book, Chapter
from ..serializers import (
    admin_book_detail,
    book_list_item,
    filter_book_fields,
    resolve_base_url,
)
from ..thumbs import rebuild_thumbs

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_dep)])

logger = logging.getLogger("admin")

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
    cached = stats_cache.get("admin_stats")
    if cached is None:
        total_books = db.execute(select(func.count(Book.id))).scalar_one()
        total_words = db.execute(
            select(func.coalesce(func.sum(Book.word_count), 0))
        ).scalar_one()
        by_cat = db.execute(
            select(Book.category, func.count(Book.id)).group_by(Book.category)
        ).all()
        by_status = db.execute(
            select(Book.status, func.count(Book.id)).group_by(Book.status)
        ).all()
        cached = {
            "total_books": total_books,
            "total_words": total_words,
            "by_category": [{"name": c, "count": n} for c, n in by_cat],
            "by_status": [{"name": s, "count": n} for s, n in by_status],
            "categories": CATEGORIES,
            # 编辑页两级分类树
            "category_tree": category_tree(),
            # 设置页展示运行环境用
            "novels_dir": str(settings.novels_dir),
            "database_path": str(settings.database_path),
            "covers_dir": str(settings.covers_dir),
        }
        stats_cache.set("admin_stats", cached)
    return {
        **cached,
        "import": get_import_status(),
        "public_base_url": resolve_base_url(request),
    }


@router.get("/stats/reading")
def admin_reading_stats(db: Session = Depends(get_db)) -> dict:
    """阅读统计：基于现有 read_at/read_percent 字段的概览（无逐日历史）。"""
    cached = stats_cache.get("reading_stats")
    if cached is not None:
        return cached
    total_books = db.execute(select(func.count(Book.id))).scalar_one()
    total_words = db.execute(
        select(func.coalesce(func.sum(Book.word_count), 0))
    ).scalar_one()

    read_books = db.execute(
        select(func.count(Book.id)).where(Book.read_at != "")
    ).scalar_one()
    finished_books = db.execute(
        select(func.count(Book.id)).where(
            and_(Book.read_at != "", Book.read_percent >= 100)
        )
    ).scalar_one()
    reading_books = db.execute(
        select(func.count(Book.id)).where(
            and_(Book.read_at != "", Book.read_percent < 100)
        )
    ).scalar_one()
    unread_books = max(0, total_books - read_books)

    read_words_raw = db.execute(
        select(func.coalesce(func.sum(Book.word_count * Book.read_percent), 0)).where(
            Book.read_at != ""
        )
    ).scalar_one()
    read_words = int(round((read_words_raw or 0) / 100))

    avg_progress = db.execute(
        select(func.coalesce(func.avg(Book.read_percent), 0)).where(Book.read_at != "")
    ).scalar_one()

    recent_books = (
        db.execute(
            select(Book)
            .where(Book.read_at != "")
            .order_by(Book.read_at.desc(), Book.id.desc())
            .limit(8)
        )
        .scalars()
        .all()
    )
    recent = [book_list_item(b) for b in recent_books]

    category_rows = db.execute(
        select(Book.category, func.count(Book.id))
        .where(Book.read_at != "")
        .group_by(Book.category)
        .order_by(func.count(Book.id).desc(), Book.category)
        .limit(12)
    ).all()

    result = {
        "total_books": total_books,
        "read_books": read_books,
        "reading_books": reading_books,
        "finished_books": finished_books,
        "unread_books": unread_books,
        "total_words": int(total_words or 0),
        "read_words": read_words,
        "avg_progress": round(float(avg_progress or 0), 1),
        "recent": recent,
        "by_category": [
            {"name": name or UNCATEGORIZED, "count": count}
            for name, count in category_rows
        ],
    }
    stats_cache.set("reading_stats", result)
    return result


class ScrapeSettingsIn(BaseModel):
    """刮削参数（设置页可调，保存到 data/scraper_settings.json）。"""

    delay: float | None = Field(default=None, ge=0.3, le=120)
    jitter_max: float | None = Field(default=None, ge=0, le=120)
    long_pause_every: int | None = Field(default=None, ge=0, le=10000)
    long_pause_min: float | None = Field(default=None, ge=0, le=600)
    long_pause_max: float | None = Field(default=None, ge=0, le=600)
    host_min_interval: float | None = Field(default=None, ge=0, le=120)
    host_jitter_max: float | None = Field(default=None, ge=0, le=120)
    retry_max: int | None = Field(default=None, ge=0, le=20)
    retry_base: float | None = Field(default=None, ge=0, le=120)
    respect_retry_after: bool | None = None


@router.get("/settings/scrape")
def admin_get_scrape_settings() -> dict:
    from .. import scraper_settings

    return {"values": scraper_settings.get_all(), "spec": scraper_settings.spec()}


@router.put("/settings/scrape")
def admin_put_scrape_settings(payload: ScrapeSettingsIn) -> dict:
    from .. import scraper_settings

    values = scraper_settings.update(payload.model_dump(exclude_none=True))
    return {"ok": True, "values": values}


class MaintenanceSettingsIn(BaseModel):
    scan_enabled: bool | None = None
    scan_interval_hours: int | None = Field(default=None, ge=1, le=720)
    scan_deep: bool | None = None


@router.get("/settings/maintenance")
def admin_get_maintenance_settings() -> dict:
    from .. import maintenance_settings

    return maintenance_settings.load()


@router.put("/settings/maintenance")
def admin_put_maintenance_settings(payload: MaintenanceSettingsIn) -> dict:
    from .. import maintenance_settings

    data = maintenance_settings.update(payload.model_dump(exclude_none=True))
    return {"ok": True, **data}


@router.get("/tasks/status")
def admin_tasks_status() -> dict:
    """导入/体检/刮削的互斥任务状态，供前端禁用按钮与提示。"""
    from ..task_guard import busy_status

    return busy_status()


@router.get("/duplicates")
def admin_duplicates(db: Session = Depends(get_db)) -> dict:
    # 与体检共用同一套重复检测，避免两处逻辑漂移
    from ..library_check import find_duplicate_groups

    items = find_duplicate_groups(db)
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
    # read=true 仅读过的书（配合 sort=read 做「继续阅读」）
    read: bool = False,
    sort: str = Query(default="updated"),  # updated|title|author|words|chapters|read
    page: int = Query(default=1, ge=1),
    # 上限放宽到 200：宽屏多列时前端会请求 cols*rows，保证非末页行占满
    page_size: int = Query(default=20, ge=1, le=200),
    # 可选字段裁剪：fields=id,name,author,cover_thumb_url
    fields: str | None = Query(default=None, max_length=500),
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
        only_read=read,
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
        "items": [filter_book_fields(book_list_item(b, base), fields) for b in books],
    }


@router.get("/books/{book_id}")
def admin_get_book(request: Request, book_id: int, db: Session = Depends(get_db)) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    return admin_book_detail(book, resolve_base_url(request))


@router.get("/books/{book_id}/search")
def admin_search_book(
    book_id: int,
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """书内搜索：扫描本书章节正文，返回章节 + 上下文片段（大小写不敏感）。

    正文优先读正文包，迁移前的旧数据回退 content 列；单章最多返回 3 条，
    总条数受 limit 限制，total 为全书实际命中数。
    """
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")
    needle = (q or "").strip()
    if not needle:
        return {"q": q, "total": 0, "items": []}

    rows = db.execute(
        select(
            Chapter.id,
            Chapter.index,
            Chapter.title,
            Chapter.content_offset,
            Chapter.content_length,
            Chapter.content,
        )
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.index)
    ).all()
    spans = [(r.content_offset or 0, r.content_length or 0) for r in rows]
    texts = read_book_texts(book_id, spans)

    lowered = needle.lower()
    items: list[dict] = []
    total = 0
    for row, pack_text in zip(rows, texts):
        text = pack_text or (row.content or "")
        if not text:
            continue
        low = text.lower()
        pos = low.find(lowered)
        per_chapter = 0
        while pos >= 0:
            total += 1
            # 单章最多 3 条，避免同一关键词刷屏
            if per_chapter < 3 and len(items) < limit:
                start = max(0, pos - 30)
                end = min(len(text), pos + len(needle) + 40)
                snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                if start > 0:
                    snippet = "…" + snippet
                if end < len(text):
                    snippet += "…"
                items.append(
                    {
                        "chapter_id": row.id,
                        "index": row.index,
                        "title": row.title,
                        # 章内字符偏移：阅读器据此滚动到匹配位置
                        "offset": pos,
                        "snippet": snippet,
                    }
                )
                per_chapter += 1
            pos = low.find(lowered, pos + len(needle))

    return {"q": needle, "total": total, "items": items}


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
    # 不在保存时移动 TXT；仅「体检 → 按分类归位」触发 relocate
    # 元数据变更后刷新更新时间，保证「导入/更新」排序准确

    def _apply() -> None:
        for k, v in data.items():
            setattr(book, k, v)
        book.updated_at = datetime.now().isoformat(timespec="seconds")

    # FTS 索引与主表不同步时触发器会报 malformed，自动重建后重试
    commit_with_fts_recovery(db, _apply)
    db.refresh(book)
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
        logger.exception("删除书籍失败 id=%s", book_id)
        raise HTTPException(500, "删除失败，请查看服务端日志") from e
    return {"ok": True, "deleted": title, "id": book_id, "fts_repaired": repaired}


class BookProgressIn(BaseModel):
    """阅读进度：百分比 0–100，可选章节序号用于续读。"""

    percent: int = Field(default=0, ge=0, le=100)
    chapter_index: int | None = Field(default=None, ge=-1)


class BatchDeleteIn(BaseModel):
    """批量删除请求体。"""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


class ThumbsRebuildIn(BaseModel):
    book_ids: list[int] | None = Field(default=None, max_length=500)
    limit: int = Field(default=200, ge=1, le=1000)
    force: bool = False
    width: int = Field(default=320, ge=120, le=800)


class BatchUpdateIn(BaseModel):
    """批量编辑：仅处理显式提供的字段。"""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)
    # 分类：两段式，category_name 非空才修改；source 为空表示本地
    category_source: str | None = Field(default=None, max_length=20)
    category_name: str | None = Field(default=None, max_length=50)
    # 标签：追加/移除/替换，空串配合 replace 可清空标签
    tags: str | None = Field(default=None, max_length=300)
    tags_mode: str = Field(default="append", pattern="^(append|remove|replace)$")
    status: str | None = Field(default=None, pattern="^(连载|完结|未知)$")


@router.post("/books/thumbs/rebuild")
def admin_rebuild_thumbs(
    payload: ThumbsRebuildIn, db: Session = Depends(get_db)
) -> dict:
    """批量回填已有封面的缩略图；可指定 book_ids，否则按 id 顺序最多处理 limit 本。"""
    stmt = select(Book).where(Book.cover_file != "")
    if payload.book_ids:
        ids = sorted({int(i) for i in payload.book_ids if i})
        if not ids:
            raise HTTPException(400, "book_ids 不能为空")
        stmt = stmt.where(Book.id.in_(ids))
    books = db.execute(stmt.order_by(Book.id).limit(payload.limit)).scalars().all()
    stats = rebuild_thumbs(books, width=payload.width, force=payload.force)
    return {"ok": True, **stats}


@router.put("/books/{book_id}/progress")
def admin_update_progress(
    request: Request, book_id: int, payload: BookProgressIn, db: Session = Depends(get_db)
) -> dict:
    """写入阅读进度百分比（阅读器/列表共用）。"""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "书籍不存在")

    def _apply() -> None:
        book.read_percent = int(payload.percent)
        if payload.chapter_index is not None:
            book.read_chapter_index = int(payload.chapter_index)
        book.read_at = datetime.now().isoformat(timespec="seconds")

    # FTS 索引与主表不同步时触发器会报 malformed，自动重建后重试
    commit_with_fts_recovery(db, _apply)
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
        logger.exception("批量删除失败 ids=%s", ids)
        raise HTTPException(500, "批量删除失败，请查看服务端日志") from e
    return {
        "ok": True,
        "deleted_count": len(titles),
        "deleted": titles,
        "ids": ids,
        "fts_repaired": repaired,
    }


@router.post("/books/batch/update")
def admin_batch_update(payload: BatchUpdateIn, db: Session = Depends(get_db)) -> dict:
    """批量编辑书籍：分类 / 标签 / 状态，未提供的字段保持不变。"""
    ids = sorted({int(i) for i in payload.ids if i and int(i) > 0})
    if not ids:
        raise HTTPException(400, "未选择书籍")
    books = [b for bid in ids if (b := db.get(Book, bid)) is not None]
    if not books:
        return {"ok": True, "updated_count": 0, "ids": []}

    tag_tokens: list[str] | None = None
    if payload.tags is not None:
        tag_tokens = [t for t in re.split(r"[,，;；\s]+", payload.tags.strip()) if t]

    now = datetime.now().isoformat(timespec="seconds")
    for book in books:
        # 先改分类：标签里的「未分类」标记依赖新分类
        if payload.category_name is not None:
            src, cat = map_site_category(payload.category_source or "", payload.category_name)
            book.category = make_category_label(src, cat or UNCATEGORIZED)
            # 显式改分类时同步书源；本地分类清空书源
            book.source = src
        if tag_tokens is not None:
            current = [t.strip() for t in (book.tags or "").split(",") if t.strip()]
            if payload.tags_mode == "replace":
                merged = list(dict.fromkeys(tag_tokens))
            elif payload.tags_mode == "remove":
                drop = set(tag_tokens)
                merged = [t for t in current if t not in drop]
            else:
                merged = list(dict.fromkeys([*current, *tag_tokens]))
            # 与导入/刮削一致：未分类补标记、已分类去标记
            book.tags = ensure_category_tag(
                ",".join(merged), book.category or UNCATEGORIZED
            )[:300]
        if payload.status:
            book.status = payload.status
        book.updated_at = now

    db.commit()
    return {"ok": True, "updated_count": len(books), "ids": [b.id for b in books]}


@router.post("/import")
def admin_import(mode: str = Query(default="local", pattern="^local$")) -> dict:
    # WebDAV 导入已移除，仅支持本地 NOVELS_DIR
    started = import_all_async("local")
    return {"started": started, "mode": "local", "import": get_import_status()}


class ImportRetryIn(BaseModel):
    # 失败项相对 NOVELS_DIR 的路径；上限与导入日志一致
    paths: list[str] = Field(..., min_length=1, max_length=500)


def _validated_retry_paths(raw_paths: list[str]) -> list[str]:
    """校验重试路径必须位于 NOVELS_DIR 内且为存在的 TXT。"""
    root = settings.novels_dir.resolve()
    valid: list[str] = []
    for raw in raw_paths:
        value = (raw or "").strip()
        if not value:
            continue
        candidate = (root / value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(400, f"重试路径不在书库目录内: {value}") from exc
        if candidate.suffix.lower() != ".txt":
            raise HTTPException(400, f"只允许重试 TXT 文件: {value}")
        if candidate.is_file():
            valid.append(str(candidate))
    if not valid:
        raise HTTPException(400, "失败文件已不存在或没有可重试的 TXT")
    return list(dict.fromkeys(valid))


@router.post("/import/retry")
def admin_import_retry(payload: ImportRetryIn) -> dict:
    """仅重试本次导入失败的文件，复用同一套后台进度/SSE。"""
    paths = _validated_retry_paths(payload.paths)
    started = import_all_async("local", only_paths=set(paths))
    return {
        "started": started,
        "mode": "local",
        "retry_count": len(paths),
        "import": get_import_status(),
    }


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
        # 持续推送直到任务结束或客户端断开（不设次数上限，长任务不丢进度）
        while True:
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
        # 持续推送直到任务结束或客户端断开（不设次数上限，长任务不丢进度）
        while True:
            if await request.is_disconnected():
                break
            st = get_batch_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")
