"""Book / Chapter → API 字典（公开与 Legado 共用）。"""
from __future__ import annotations

from .config import settings
from .models import Book, Chapter


def cover_abs(book: Book) -> str:
    if not book.cover_file:
        return ""
    return f"{settings.public_base_url}/covers/{book.cover_file}"


def book_list_item(book: Book) -> dict:
    return {
        "id": book.id,
        "name": book.title,
        "author": book.author,
        "category": book.category,
        "tags": book.tags_list,
        "status": book.status,
        "source": getattr(book, "source", "") or "",
        "source_id": getattr(book, "source_id", "") or "",
        "cover_url": cover_abs(book),
        "intro": (book.intro or "")[:160],
        "word_count": book.word_count,
        "chapter_count": book.chapter_count,
        "latest_chapter": book.latest_chapter,
        "detail_url": f"{settings.public_base_url}/api/books/{book.id}",
        "toc_url": f"{settings.public_base_url}/api/books/{book.id}/chapters",
        "updated_at": book.updated_at,
    }


def book_detail(book: Book, with_chapters: bool = False) -> dict:
    data = book_list_item(book)
    data["intro"] = book.intro or ""
    data["source_path"] = book.source_path
    data["created_at"] = book.created_at
    if with_chapters:
        data["chapters"] = [chapter_item(ch) for ch in book.chapters]
    return data


def chapter_item(ch: Chapter) -> dict:
    return {
        "id": ch.id,
        "index": ch.index,
        "name": ch.title,
        "content_url": f"{settings.public_base_url}/api/books/{ch.book_id}/chapters/{ch.id}",
        "legado_content_url": f"{settings.public_base_url}/api/legado/content/{ch.book_id}/{ch.id}",
    }


def chapter_content(ch: Chapter) -> dict:
    return {
        "id": ch.id,
        "book_id": ch.book_id,
        "index": ch.index,
        "title": ch.title,
        "content": ch.content,
        "content_url": f"{settings.public_base_url}/api/books/{ch.book_id}/chapters/{ch.id}",
    }


def admin_book_detail(book: Book) -> dict:
    data = book_detail(book, with_chapters=False)
    data["cover_file"] = book.cover_file
    data["source_hash"] = book.source_hash
    data["source"] = getattr(book, "source", "") or ""
    data["source_id"] = getattr(book, "source_id", "") or ""
    data["chapters_preview"] = [
        {"id": c.id, "index": c.index, "title": c.title}
        for c in book.chapters[:30]
    ]
    return data
