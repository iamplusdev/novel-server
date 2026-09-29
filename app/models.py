"""SQLite 数据模型：Book + Chapter + ImportLog，字段极少、够用即可。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(100), default="佚名", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), default="未分类", nullable=False, index=True)
    intro: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="完结", nullable=False)  # 连载/完结/未知
    tags: Mapped[str] = mapped_column(String(300), default="", nullable=False)  # 逗号分隔
    cover_file: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latest_chapter: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="", nullable=False)  # 起点 / 番茄 …
    source_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)  # 站外 bookId
    created_at: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: Mapped[str] = mapped_column(String(30), default=lambda: datetime.now().isoformat(timespec="seconds"))

    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.index",
        # 懒加载：列表/元数据接口不再连带拉取全部章节正文
        lazy="select",
    )

    @property
    def tags_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def cover_url(self) -> str:
        if not self.cover_file:
            return ""
        return f"{settings_public()}/covers/{self.cover_file}"

    @property
    def detail_url(self) -> str:
        return f"{settings_public()}/api/books/{self.id}"

    @property
    def toc_url(self) -> str:
        return f"{settings_public()}/api/books/{self.id}/chapters"


def settings_public() -> str:
    from .config import settings

    return settings.public_base_url


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # 遗留正文列：迁移后保持为空；读正文优先走 content_store 偏移
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 正文包（data/contents/{book_id}.bin）内字节偏移/长度；char_len 供统计与体检
    content_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    book: Mapped[Book] = relationship("Book", back_populates="chapters")

    @property
    def content_url(self) -> str:
        return f"{settings_public()}/api/books/{self.book_id}/chapters/{self.id}"


Index("ix_chapters_book_index", Chapter.book_id, Chapter.index)


class ImportLog(Base):
    """一次导入任务的结果日志（历史可按日期查询）。"""

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ISO8601 秒级，如 2026-09-28T14:32:01
    started_at: Mapped[str] = mapped_column(String(30), default="", nullable=False, index=True)
    finished_at: Mapped[str] = mapped_column(String(30), default="", nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(20), default="local", nullable=False)
    summary: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_n: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_n: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_n: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_n: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 明细 JSON：{added:[], updated:[], skipped:[], failed:[], recent:[]}
    detail: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    @property
    def detail_dict(self) -> dict:
        try:
            data = json.loads(self.detail or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
