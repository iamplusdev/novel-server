"""Book / Chapter → API 字典（公开与 Legado 共用）。

绝对地址优先按请求 Host / X-Forwarded-Host 推导，避免域名部署后仍指向 127.0.0.1；
管理端另给相对 cover_path，同源访问不依赖域名配置。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import object_session

from .config import normalize_source, parse_category_label, settings
from .models import Book, Chapter


def resolve_base_url(request=None) -> str:
    """推导对外基址：反代头优先，否则回退 PUBLIC_BASE_URL。"""
    if request is None:
        return settings.public_base_url
    try:
        headers = request.headers
        proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        host = (headers.get("x-forwarded-host") or "").split(",")[0].strip()
        if not host:
            host = (headers.get("host") or "").strip()
        if host:
            if not proto:
                proto = getattr(getattr(request, "url", None), "scheme", None) or "http"
            return f"{proto}://{host}".rstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return settings.public_base_url


def cover_rel(book: Book) -> str:
    """相对封面路径，管理端同源加载用。"""
    if not book.cover_file:
        return ""
    return f"/covers/{book.cover_file}"


def cover_abs(book: Book, base: str | None = None) -> str:
    if not book.cover_file:
        return ""
    root = (base or settings.public_base_url).rstrip("/")
    return f"{root}/covers/{book.cover_file}"


def book_list_item(book: Book, base: str | None = None) -> dict:
    root = (base or settings.public_base_url).rstrip("/")
    return {
        "id": book.id,
        "name": book.title,
        # title 与 name 同值：体检/重复报告用 title，列表用 name，契约统一
        "title": book.title,
        "author": book.author,
        "category": book.category,
        "tags": book.tags_list,
        "status": book.status,
        "source": getattr(book, "source", "") or "",
        "source_id": getattr(book, "source_id", "") or "",
        "cover_path": cover_rel(book),
        "cover_url": cover_abs(book, root),
        "intro": (book.intro or "")[:160],
        "word_count": book.word_count,
        "chapter_count": book.chapter_count,
        "latest_chapter": book.latest_chapter,
        "detail_url": f"{root}/api/books/{book.id}",
        "toc_url": f"{root}/api/books/{book.id}/chapters",
        "updated_at": book.updated_at,
        # 阅读进度百分比（0–100），列表卡片展示用
        "read_percent": int(getattr(book, "read_percent", 0) or 0),
    }


def book_detail(book: Book, with_chapters: bool = False, base: str | None = None) -> dict:
    data = book_list_item(book, base)
    data["intro"] = book.intro or ""
    data["source_path"] = book.source_path
    data["created_at"] = book.created_at
    # 阅读续读信息（章节序号 + 最近阅读时间）
    data["read_chapter_index"] = int(getattr(book, "read_chapter_index", -1) if getattr(book, "read_chapter_index", -1) is not None else -1)
    data["read_at"] = getattr(book, "read_at", "") or ""
    if with_chapters:
        data["chapters"] = [chapter_item(ch, base) for ch in book.chapters]
    return data


def chapter_item(ch, base: str | None = None) -> dict:
    """目录条目：仅需 id/book_id/index/title，避免加载正文。"""
    root = (base or settings.public_base_url).rstrip("/")
    return {
        "id": ch.id,
        "index": ch.index,
        "name": ch.title,
        # title 与 name 同值，与 chapters_preview 对齐
        "title": ch.title,
        "content_url": f"{root}/api/books/{ch.book_id}/chapters/{ch.id}",
        "legado_content_url": f"{root}/api/legado/content/{ch.book_id}/{ch.id}",
    }


def chapter_content(ch: Chapter, base: str | None = None) -> dict:
    root = (base or settings.public_base_url).rstrip("/")
    # 正文优先读正文包偏移；迁移前旧数据回退 content 列
    from .content_store import read_chapter_text

    text = read_chapter_text(
        ch.book_id,
        ch.content_offset,
        ch.content_length,
        legacy_content=ch.content,
    )
    return {
        "id": ch.id,
        "book_id": ch.book_id,
        "index": ch.index,
        "title": ch.title,
        "content": text,
        "content_url": f"{root}/api/books/{ch.book_id}/chapters/{ch.id}",
    }


def admin_book_detail(book: Book, base: str | None = None) -> dict:
    data = book_detail(book, with_chapters=False, base=base)
    data["cover_file"] = book.cover_file
    data["source_hash"] = book.source_hash
    data["source"] = getattr(book, "source", "") or ""
    data["source_id"] = getattr(book, "source_id", "") or ""
    # 两级分类：category 合成串 + 拆开的书源/栏目（编辑页下拉用）
    src_name, cat_name = parse_category_label(book.category or "")
    if not src_name:
        src_name = normalize_source(getattr(book, "source", "") or "")
    data["category"] = book.category or ""
    data["category_source"] = src_name  # ""=本地 / 起点 / 番茄
    data["category_name"] = cat_name
    # 只取前 30 章标题做预览，避免 lazy 加载全部章节正文
    session = object_session(book)
    preview: list[dict] = []
    if session is not None:
        rows = session.execute(
            select(Chapter.id, Chapter.index, Chapter.title)
            .where(Chapter.book_id == book.id)
            .order_by(Chapter.index)
            .limit(30)
        ).all()
        preview = [{"id": r.id, "index": r.index, "title": r.title} for r in rows]
    data["chapters_preview"] = preview
    return data
