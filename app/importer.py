"""扫描 novels/<分类>/*.txt 并写入 SQLite。文件内容哈希未变则跳过。"""
from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import CATEGORIES, settings
from .database import SessionLocal
from .models import Book, Chapter
from .parsers import load_txt_book


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"新增 {len(self.added)} · 更新 {len(self.updated)} · "
            f"跳过 {len(self.skipped)} · 失败 {len(self.failed)}"
        )

    def to_dict(self) -> dict:
        return {
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "summary": self.summary,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }


_import_lock = threading.Lock()
_import_status: dict = {"running": False, "last": None}


def get_import_status() -> dict:
    return dict(_import_status)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


_SKIP_NAMES = {
    "readme.txt",
    "readme.md",
    "license.txt",
    ".gitkeep",
    ".ds_store",
}


def _iter_txt_files(root: Path):
    """yield (category, path)。分类 = novels 下的子目录名，根目录散落文件归「未分类」。"""
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if child.is_file() and child.suffix.lower() == ".txt":
            if child.name.lower() in _SKIP_NAMES:
                continue
            yield "未分类", child
        elif child.is_dir():
            if child.name.startswith("."):
                continue
            cat = child.name.strip() or "未分类"
            for f in sorted(child.rglob("*.txt")):
                if f.is_file() and f.name.lower() not in _SKIP_NAMES:
                    yield cat, f


def _find_book_by_source(db: Session, source_path: str) -> Book | None:
    return db.execute(select(Book).where(Book.source_path == source_path)).scalar_one_or_none()


def _find_book_by_hash(db: Session, content_hash: str) -> Book | None:
    if not content_hash:
        return None
    return db.execute(select(Book).where(Book.source_hash == content_hash)).scalar_one_or_none()


def _find_book_by_title_author(db: Session, title: str, author: str) -> Book | None:
    if not title:
        return None
    return db.execute(
        select(Book).where(Book.title == title, Book.author == (author or "佚名"))
    ).scalars().first()


def _upsert_book(db: Session, path: Path, category: str, content_hash: str) -> tuple[str, str]:
    """返回 (action, label) action in added|updated|skipped"""
    rel = str(path)
    label = f"{category}/{path.stem}"
    existing = _find_book_by_source(db, rel)
    if existing and existing.source_hash == content_hash:
        return "skipped", label

    parsed = load_txt_book(path, category)

    # 防重复：同内容哈希，或同书名+作者（避免换路径/刮削改名后再导入变两本）
    if not existing:
        existing = _find_book_by_hash(db, content_hash) or _find_book_by_title_author(
            db, parsed.title, parsed.author
        )
        if existing:
            # 指向最新路径
            existing.source_path = rel

    if existing and existing.source_hash == content_hash and existing.source_path == rel:
        return "skipped", label

    if existing:
        book = existing
        book.title = parsed.title or book.title
        book.author = parsed.author or book.author
        book.category = category
        book.word_count = parsed.word_count
        book.source_hash = content_hash
        book.updated_at = datetime.now().isoformat(timespec="seconds")
        # 仅当简介为空时自动填充
        if not book.intro:
            book.intro = parsed.intro
        db.query(Chapter).filter(Chapter.book_id == book.id).delete()
        action = "updated"
    else:
        book = Book(
            title=parsed.title,
            author=parsed.author,
            category=category,
            intro=parsed.intro,
            status="完结",
            tags="",
            cover_file="",
            source_path=rel,
            source_hash=content_hash,
            word_count=parsed.word_count,
        )
        db.add(book)
        db.flush()
        action = "added"

    for i, ch in enumerate(parsed.chapters, start=0):
        db.add(
            Chapter(
                book_id=book.id,
                index=i,
                title=re.sub(r"\s+", " ", ch.title).strip()[:200],
                content=ch.content,
            )
        )

    book.chapter_count = len(parsed.chapters)
    book.latest_chapter = parsed.chapters[-1].title[:200] if parsed.chapters else ""
    return action, f"{category}/{book.title}"


def import_all(db: Session | None = None) -> ImportResult:
    own = db is None
    if own:
        db = SessionLocal()
    result = ImportResult()
    root = settings.novels_dir
    try:
        files = list(_iter_txt_files(root))
        for category, path in files:
            try:
                digest = file_sha256(path)
                action, label = _upsert_book(db, path, category, digest)
                getattr(result, action).append(label)
            except Exception as exc:  # noqa: BLE001 — 导入器要尽量吞掉单文件错误
                result.failed.append(f"{path.name}: {exc}")
        db.commit()
    finally:
        if own:
            db.close()
    return result


def import_all_async() -> bool:
    """后台线程导入，避免阻塞 HTTP。已在跑则返回 False。"""
    global _import_status
    if not _import_lock.acquire(blocking=False):
        return False
    if _import_status.get("running"):
        _import_lock.release()
        return False

    def _run() -> None:
        global _import_status
        _import_status = {"running": True, "last": None, "started_at": datetime.now().isoformat(timespec="seconds")}
        try:
            result = import_all()
            _import_status = {"running": False, "last": result.to_dict()}
        except Exception as exc:  # noqa: BLE001
            _import_status = {
                "running": False,
                "last": {
                    "added": [],
                    "updated": [],
                    "skipped": [],
                    "failed": [str(exc)],
                    "summary": f"导入失败: {exc}",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
            }
        finally:
            _import_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return True


# 供 CLI / 测试使用：确保分类文件夹存在
def ensure_category_dirs() -> None:
    settings.novels_dir.mkdir(parents=True, exist_ok=True)
    for c in CATEGORIES:
        (settings.novels_dir / c).mkdir(parents=True, exist_ok=True)
