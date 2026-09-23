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
from .parsers import load_txt_book, load_txt_book_from_text

# 「未分类」既是分类名，也是导入时打在 tags 上的标记，便于后续筛选/归位
UNCATEGORIZED = "未分类"


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


def _ensure_category_tag(tags: str, category: str) -> str:
    """按分类维护「未分类」标记：归入未分类则补上，已正式分类则去掉。"""
    items = [t.strip() for t in (tags or "").split(",") if t.strip()]
    items = [t for t in items if t != UNCATEGORIZED]
    if category == UNCATEGORIZED:
        items.insert(0, UNCATEGORIZED)
    return ",".join(items[:12])


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
        book.word_count = parsed.word_count
        book.source_hash = content_hash
        book.source_path = source_key
        book.updated_at = datetime.now().isoformat(timespec="seconds")
        # 未分类文件夹导入时补「未分类」标签，便于后续筛选
        book.tags = _ensure_category_tag(book.tags, category)
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
            # 未分类入库即打标记
            tags=_ensure_category_tag("", category),
            cover_file="",
            source_path=source_key,
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
    try:
        files = list(_iter_txt_files(root))
        for category, path in files:
            try:
                digest = file_sha256(path)
                action, label = _upsert_book(db, path, category, digest)
                getattr(result, action).append(label)
            except Exception as exc:  # noqa: BLE001
                result.failed.append(f"{path.name}: {exc}")
        db.commit()
    finally:
        if own:
            db.close()
    return result


def import_from_webdav(db: Session | None = None) -> ImportResult:
    """从 WebDAV 的 books/<分类>/*.txt 增量导入（章节仍写入 SQLite）。"""
    from .backup import load_config
    from .webdav import WebDAVClient, WebDAVError

    cfg = load_config()
    if not cfg.webdav_url:
        raise WebDAVError("请先在「备份」页配置 WebDAV 地址")

    client = WebDAVClient(cfg.webdav_url, cfg.username, cfg.password, timeout=120)
    result = ImportResult()
    own = db is None
    if own:
        db = SessionLocal()

    skip_names = {"readme.txt", "readme.md", "license.txt", ".gitkeep", ".ds_store"}
    # 书籍根目录可配置：相对 WebDAV 根，如 books / 小说仓库/novels
    root = (cfg.books_path or "books").strip().strip("/").replace("\\", "/") or "books"

    def _discover() -> str:
        try:
            top = client.list_dir_names("")
            hint = "、".join(top[:20]) if top else "(空)"
            return f"WebDAV 根目录下有：{hint}"
        except WebDAVError as e:
            return f"无法列出 WebDAV 根目录：{e}"

    # 路径探测：逐级尝试，容错尾斜杠/多一层前缀
    def _resolve_root() -> str:
        candidates = [root, root.strip("/")]
        # 去掉重复段
        seen = []
        for c in candidates:
            if c and c not in seen:
                seen.append(c)
        for cand in seen:
            if client.exists(cand):
                return cand
        # 尝试在根下查找最后一段
        last = root.rsplit("/", 1)[-1]
        try:
            top = client.list_dir_names("")
        except WebDAVError:
            top = []
        if last in top:
            return last
        for name in top:
            try:
                subs = client.list_dir_names(name)
            except WebDAVError:
                continue
            if last in subs:
                return f"{name}/{last}"
            if root in subs or root.rsplit("/", 1)[-1] in subs:
                return f"{name}/{root.rsplit('/', 1)[-1]}"
        raise WebDAVError(
            f"WebDAV 书籍目录不存在或无权限：{root}。{_discover()}。"
            f"请在「备份」页把「书籍目录」改成相对 WebDAV 根的路径（不要带 https 与 /dav 前缀）。"
        )

    try:
        try:
            root = _resolve_root()
        except WebDAVError as e:
            result.failed.append(str(e))
            return result

        def walk(rel_dir: str, category: str) -> None:
            try:
                items = client.list_items(rel_dir)
            except WebDAVError as e:
                result.failed.append(f"{rel_dir}: {e}")
                return
            at_books_root = rel_dir.rstrip("/") in ("", root)
            for it in items:
                remote = f"{rel_dir.rstrip('/')}/{it.name}" if rel_dir else it.name
                if it.is_dir:
                    sub_cat = (it.name.strip() or category) if at_books_root else category
                    walk(remote, sub_cat)
                    continue
                name_l = it.name.lower()
                if not name_l.endswith(".txt") or name_l in skip_names:
                    continue
                src = f"webdav:{remote}"
                cat = category if category and category != root else "未分类"
                label = f"{cat}/{Path(it.name).stem}"
                try:
                    raw = client.get_file(remote)
                    digest = _bytes_sha256(raw)
                    text = decode_txt_bytes(raw)
                    parsed = load_txt_book_from_text(text, Path(it.name).stem, cat)
                    action, lab = _upsert_parsed(db, src, cat, parsed, digest)
                    getattr(result, action).append(lab or label)
                except Exception as exc:  # noqa: BLE001
                    result.failed.append(f"{label}: {exc}")

        walk(root, "未分类")
        db.commit()
    finally:
        # 路径探测失败也必须关闭自建会话，避免连接泄漏
        if own:
            db.close()
    return result


def import_all_async(mode: str = "local") -> bool:
    """后台线程导入。mode: local | webdav | both"""
    global _import_status
    if not _import_lock.acquire(blocking=False):
        return False
    if _import_status.get("running"):
        _import_lock.release()
        return False

    def _merge(a: ImportResult, b: ImportResult) -> ImportResult:
        return ImportResult(
            added=a.added + b.added,
            updated=a.updated + b.updated,
            skipped=a.skipped + b.skipped,
            failed=a.failed + b.failed,
        )

    def _run() -> None:
        global _import_status
        _import_status = {
            "running": True,
            "mode": mode,
            "last": None,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            if mode == "webdav":
                result = import_from_webdav()
            elif mode == "both":
                result = _merge(import_all(), import_from_webdav())
            else:
                result = import_all()
            _import_status = {"running": False, "mode": mode, "last": result.to_dict()}
        except Exception as exc:  # noqa: BLE001
            _import_status = {
                "running": False,
                "mode": mode,
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
