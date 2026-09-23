"""扫描 novels/<书源>/<分类>/*.txt（兼容旧 novels/<分类>/*.txt）并写入 SQLite。

目录格式（本地与 WebDAV 一致）：
  novels/起点/都市/书名.txt
  novels/番茄/西方奇幻/书名.txt
  novels/未分类/书名.txt
"""
from __future__ import annotations

import hashlib
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import (
    SOURCE_CATEGORIES,
    UNCATEGORIZED,
    category_rel_parts,
    parse_category_label,
    settings,
)
from .database import SessionLocal
from .models import Book, Chapter
from .parsers import load_txt_book, load_txt_book_from_text

# 兼容旧导入
CATEGORIES = list(SOURCE_CATEGORIES.keys())


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
# 请求中止导入（A6）
_import_cancel = threading.Event()


def get_import_status() -> dict:
    out = dict(_import_status)
    out["cancel_requested"] = _import_cancel.is_set()
    return out


def request_import_cancel() -> bool:
    """请求停止当前导入；运行中才有效。"""
    if not _import_status.get("running"):
        return False
    _import_cancel.set()
    return True


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
    """yield (category_label, path)。

    优先识别两级「书源/分类」，兼容旧一级「分类」；根目录散落文件归「未分类」。
    """
    if not root.exists():
        return

    def _walk_dir(d: Path, label: str):
        for f in sorted(d.rglob("*.txt")):
            if f.is_file() and f.name.lower() not in _SKIP_NAMES:
                yield label, f

    for child in sorted(root.iterdir()):
        if child.is_file() and child.suffix.lower() == ".txt":
            if child.name.lower() in _SKIP_NAMES:
                continue
            yield UNCATEGORIZED, child
            continue
        if not child.is_dir() or child.name.startswith("."):
            continue
        name = child.name.strip() or UNCATEGORIZED
        # 两级：novels/起点/都市/、novels/番茄/西方奇幻/
        if name in SOURCE_CATEGORIES:
            subs = [p for p in sorted(child.iterdir()) if p.is_dir() and not p.name.startswith(".")]
            if subs:
                for sub in subs:
                    label = f"{name}-{sub.name.strip() or UNCATEGORIZED}"
                    yield from _walk_dir(sub, label)
                # 书源目录下散落 txt
                for f in sorted(child.glob("*.txt")):
                    if f.is_file() and f.name.lower() not in _SKIP_NAMES:
                        yield f"{name}-{UNCATEGORIZED}", f
                continue
        # 兼容旧一级分类目录（含书源目录下无子分类时）
        yield from _walk_dir(child, name)


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


def ensure_category_tag(tags: str, category: str) -> str:
    """按分类维护「未分类」标记：归入未分类则补上，已正式分类则去掉。"""
    items = [t.strip() for t in (tags or "").split(",") if t.strip()]
    items = [t for t in items if t != UNCATEGORIZED]
    if category == UNCATEGORIZED:
        items.insert(0, UNCATEGORIZED)
    return ",".join(items[:12])


# 兼容旧内部调用
_ensure_category_tag = ensure_category_tag


def _upsert_parsed(
    db: Session,
    source_key: str,
    category: str,
    parsed,
    content_hash: str,
) -> tuple[str, str]:
    """写入/更新一本书。source_key 为本地路径或 webdav:... 标识。"""
    label = f"{category}/{parsed.title}"
    existing = _find_book_by_source(db, source_key)
    if existing and existing.source_hash == content_hash:
        return "skipped", label

    if not existing:
        existing = _find_book_by_hash(db, content_hash) or _find_book_by_title_author(
            db, parsed.title, parsed.author
        )
        if existing:
            existing.source_path = source_key

    if existing and existing.source_hash == content_hash and existing.source_path == source_key:
        return "skipped", label

    if existing:
        book = existing
        book.title = parsed.title or book.title
        book.author = parsed.author or book.author
        book.category = category
        # 目录含书源前缀时同步 source（番茄-西方奇幻 → 番茄）
        src_name, _rest = parse_category_label(category)
        if src_name:
            book.source = src_name
        book.word_count = parsed.word_count
        book.source_hash = content_hash
        book.source_path = source_key
        book.updated_at = datetime.now().isoformat(timespec="seconds")
        # 未分类文件夹导入时补「未分类」标签，便于后续筛选
        book.tags = _ensure_category_tag(book.tags, category)
        if not book.intro:
            book.intro = parsed.intro
        # 先清旧章节再写入（SQLAlchemy 2.x 风格）
        db.execute(delete(Chapter).where(Chapter.book_id == book.id))
        action = "updated"
    else:
        src_name, _rest = parse_category_label(category)
        book = Book(
            title=parsed.title,
            author=parsed.author,
            category=category,
            intro=parsed.intro,
            status="完结",
            # 未分类入库即打标记
            tags=_ensure_category_tag("", category),
            cover_file="",
            source_path=source_key,
            source_hash=content_hash,
            word_count=parsed.word_count,
            source=src_name,
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


def relocate_local_txt(book: Book) -> bool:
    """把 TXT 归位到 <书源>/<分类>/（本地 novels/ 与 WebDAV books/ 同构），并更新 source_path。

    支持本地路径与 webdav: 相对路径；返回是否发生了移动。
    """
    sp = (book.source_path or "").strip()
    if not sp:
        return False
    parts = category_rel_parts(book.category or UNCATEGORIZED)
    if sp.startswith("webdav:"):
        return _relocate_webdav_txt(book, sp[len("webdav:") :].lstrip("/"), parts)
    return _relocate_local_txt(book, Path(sp), parts)


def _relocate_local_txt(book: Book, src: Path, parts: tuple[str, ...]) -> bool:
    """本地 TXT → novels/<书源>/<分类>/。"""
    if not src.is_file():
        return False
    dest_dir = settings.novels_dir.joinpath(*parts)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    try:
        if dest.resolve() == src.resolve():
            return False
        if dest.exists():
            dest = dest_dir / f"{src.stem}_{book.id}{src.suffix}"
        shutil.move(str(src), str(dest))
    except OSError:
        return False
    book.source_path = str(dest)
    return True


def _relocate_webdav_txt(book: Book, src_rel: str, parts: tuple[str, ...]) -> bool:
    """WebDAV TXT → books/<书源>/<分类>/（MOVE），成功则更新 source_path。"""
    if not src_rel:
        return False
    try:
        from .backup import load_config
        from .webdav import WebDAVClient
    except Exception:  # noqa: BLE001
        return False
    cfg = load_config()
    if not cfg.webdav_url:
        return False
    try:
        client = WebDAVClient(cfg.webdav_url, cfg.username, cfg.password, timeout=120)
        root = (cfg.books_path or "books").strip().strip("/").replace("\\", "/") or "books"
        fname = src_rel.rsplit("/", 1)[-1]
        if not fname:
            return False
        dest_parent = "/".join([root, *parts])
        src_parent = src_rel.rsplit("/", 1)[0] if "/" in src_rel else ""
        # 已在目标目录则跳过
        if src_parent.rstrip("/") == dest_parent.rstrip("/"):
            return False
        dest_rel = f"{dest_parent}/{fname}"
        # 目标已存在则改名，避免 MOVE 冲突
        if client.exists(dest_rel):
            stem, dot, ext = fname.rpartition(".")
            if not dot:
                stem, ext = fname, ""
            dest_rel = f"{dest_parent}/{stem}_{book.id}{dot}{ext}"
        client.move(src_rel, dest_rel, overwrite=False)
        book.source_path = f"webdav:{dest_rel}"
        return True
    except Exception:  # noqa: BLE001
        # 远端失败不阻断库内写入
        return False


def _upsert_book(db: Session, path: Path, category: str, content_hash: str) -> tuple[str, str]:
    parsed = load_txt_book(path, category)
    return _upsert_parsed(db, str(path), category, parsed, content_hash)


def _bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_txt_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def import_all(db: Session | None = None) -> ImportResult:
    own = db is None
    if own:
        db = SessionLocal()
    result = ImportResult()
    root = settings.novels_dir
    # 分批提交：大库中途崩溃时已入库部分不丢
    batch_size = 10
    pending = 0
    try:
        files = list(_iter_txt_files(root))
        for category, path in files:
            # 支持中途取消（A6）
            if _import_cancel.is_set():
                result.failed.append("（已取消）")
                break
            try:
                digest = file_sha256(path)
                action, label = _upsert_book(db, path, category, digest)
                getattr(result, action).append(label)
                pending += 1
                if pending >= batch_size:
                    db.commit()
                    pending = 0
            except Exception as exc:  # noqa: BLE001
                result.failed.append(f"{path.name}: {exc}")
                # 单本失败不影响整批，回滚脏对象后继续
                db.rollback()
                pending = 0
        db.commit()
    finally:
        if own:
            db.close()
    return result


def import_all_async(mode: str = "local") -> bool:
    """后台线程导入（仅本地 NOVELS_DIR；WebDAV 导入已移除）。"""
    global _import_status
    if not _import_lock.acquire(blocking=False):
        return False
    if _import_status.get("running"):
        _import_lock.release()
        return False
    _import_cancel.clear()

    def _run() -> None:
        global _import_status
        _import_status = {
            "running": True,
            "mode": "local",
            "last": None,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            result = import_all()
            _import_status = {"running": False, "mode": "local", "last": result.to_dict()}
        except Exception as exc:  # noqa: BLE001
            _import_status = {
                "running": False,
                "mode": "local",
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


# 供 CLI / 测试使用：确保「书源/分类」文件夹存在
def ensure_category_dirs() -> None:
    settings.novels_dir.mkdir(parents=True, exist_ok=True)
    for src, cats in SOURCE_CATEGORIES.items():
        for c in cats:
            (settings.novels_dir / src / c).mkdir(parents=True, exist_ok=True)
    (settings.novels_dir / UNCATEGORIZED).mkdir(parents=True, exist_ok=True)
