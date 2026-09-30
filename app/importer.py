"""扫描 novels/<书源>/<分类>/*.txt 与 novels/未分类/*.txt 并写入 SQLite。

目录格式（本地与 WebDAV 一致）：
  novels/起点/都市/书名.txt
  novels/番茄/西方奇幻/书名.txt
  novels/未分类/书名.txt

只扫描「书源」目录与「未分类」目录；其他目录与根目录散落 txt 不导入。
"""
from __future__ import annotations

import hashlib
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from .config import (
    SOURCE_CATEGORIES,
    UNCATEGORIZED,
    category_rel_parts,
    parse_category_label,
    settings,
)
from .content_store import write_pack
from .database import SessionLocal
from .models import Book, Chapter, ImportLog
from .parsers import load_txt_book, load_txt_book_from_text

# 兼容旧导入
CATEGORIES = list(SOURCE_CATEGORIES.keys())


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    # 最近处理记录（带动作前缀），用于导入进度展示
    recent_log: list[str] = field(default_factory=list)

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
_status_lock = threading.Lock()
# 实时进度字段：total/done/current/percent/added_n/updated_n/skipped_n/failed_n/recent
_import_status: dict = {
    "running": False,
    "last": None,
    "total": 0,
    "done": 0,
    "current": "",
    "percent": 0,
    "added_n": 0,
    "updated_n": 0,
    "skipped_n": 0,
    "failed_n": 0,
    "recent": [],
}
# 请求中止导入（A6）
_import_cancel = threading.Event()


def _set_import_status(**fields) -> None:
    """原子合并导入状态字段（进度与 SSE 读取并发安全）。"""
    global _import_status
    with _status_lock:
        _import_status = {**_import_status, **fields}


def get_import_status() -> dict:
    with _status_lock:
        out = dict(_import_status)
        out["recent"] = list(_import_status.get("recent") or [])
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

    只扫描「书源」目录（起点/番茄/纵横）与「未分类」目录：
      novels/起点/都市/书名.txt
      novels/未分类/书名.txt
    其他目录（含旧一级分类、备份等）与根目录散落 txt 一律跳过。
    """
    if not root.exists():
        return

    def _walk_dir(d: Path, label: str):
        for f in sorted(d.rglob("*.txt")):
            if f.is_file() and f.name.lower() not in _SKIP_NAMES:
                yield label, f

    # 仅允许的顶层目录：书源目录 + 未分类；其余文件夹不扫描
    allowed_top = set(SOURCE_CATEGORIES.keys()) | {UNCATEGORIZED}

    for child in sorted(root.iterdir()):
        # 根目录散落 txt 不导入
        if not child.is_dir() or child.name.startswith("."):
            continue
        name = child.name.strip() or UNCATEGORIZED
        if name not in allowed_top:
            continue
        # 未分类：递归扫其下 txt
        if name == UNCATEGORIZED:
            yield from _walk_dir(child, UNCATEGORIZED)
            continue
        # 两级：novels/起点/都市/、novels/番茄/西方奇幻/
        subs = [p for p in sorted(child.iterdir()) if p.is_dir() and not p.name.startswith(".")]
        if subs:
            for sub in subs:
                label = f"{name}-{sub.name.strip() or UNCATEGORIZED}"
                yield from _walk_dir(sub, label)
            # 书源目录下散落 txt 归该书源-未分类
            for f in sorted(child.glob("*.txt")):
                if f.is_file() and f.name.lower() not in _SKIP_NAMES:
                    yield f"{name}-{UNCATEGORIZED}", f
            continue
        # 书源目录下无子分类时，直接扫书源目录内 txt
        yield from _walk_dir(child, f"{name}-{UNCATEGORIZED}")


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

    # 正文写入独立正文包，库内只存字节偏移/长度（千章级批量插入）
    chapter_payloads = parsed.chapters
    spans = write_pack(book.id, [c.content for c in chapter_payloads])
    rows = []
    for i, (ch, (off, blen, clen)) in enumerate(zip(chapter_payloads, spans)):
        rows.append(
            {
                "book_id": book.id,
                "index": i,
                "title": re.sub(r"\s+", " ", ch.title).strip()[:200],
                # 不再把正文写入 SQLite
                "content": "",
                "content_offset": off,
                "content_length": blen,
                "content_chars": clen,
            }
        )
    if rows:
        db.execute(insert(Chapter), rows)

    book.chapter_count = len(parsed.chapters)
    book.latest_chapter = parsed.chapters[-1].title[:200] if parsed.chapters else ""
    return action, f"{category}/{book.title}"


def relocate_local_txt(book: Book) -> bool:
    """把本地 TXT 归位到 novels/<书源>/<分类>/，并更新 source_path。

    仅处理本地路径；webdav: 前缀的历史数据跳过。返回是否发生了移动。
    """
    sp = (book.source_path or "").strip()
    if not sp or sp.startswith("webdav:"):
        return False
    parts = category_rel_parts(book.category or UNCATEGORIZED)
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


def _progress_fields(result: ImportResult, total: int, done: int, current: str) -> dict:
    """组装进度字段，供前端进度条/日志使用。"""
    percent = int(done * 100 / total) if total else (100 if done else 0)
    recent = list(result.recent_log[-8:])
    return {
        "total": total,
        "done": done,
        "current": current,
        "percent": percent,
        "added_n": len(result.added),
        "updated_n": len(result.updated),
        "skipped_n": len(result.skipped),
        "failed_n": len(result.failed),
        "recent": recent,
    }


def import_all(db: Session | None = None) -> ImportResult:
    import logging

    log = logging.getLogger("importer")
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
        total = len(files)
        log.info("导入开始：%s 个 TXT", total)
        _set_import_status(**_progress_fields(result, total, 0, ""))
        for done, (category, path) in enumerate(files, start=1):
            # 支持中途取消（A6）
            if _import_cancel.is_set():
                result.failed.append("（已取消）")
                result.recent_log.append("取消")
                _set_import_status(**_progress_fields(result, total, done - 1, ""))
                break
            current_name = path.name
            _set_import_status(**_progress_fields(result, total, done - 1, current_name))
            try:
                digest = file_sha256(path)
                action, label = _upsert_book(db, path, category, digest)
                getattr(result, action).append(label)
                mark = {"added": "+", "updated": "~", "skipped": "·", "failed": "!"}.get(action, "?")
                result.recent_log.append(f"{mark} {label}")
                pending += 1
                if pending >= batch_size:
                    db.commit()
                    pending = 0
            except Exception as exc:  # noqa: BLE001
                err_label = f"{path.name}: {exc}"
                log.warning("导入失败 %s: %s", path, exc)
                result.failed.append(err_label)
                result.recent_log.append(f"! {err_label}")
                # 单本失败不影响整批，回滚脏对象后继续
                db.rollback()
                pending = 0
            _set_import_status(**_progress_fields(result, total, done, current_name))
        db.commit()
        log.info("导入结束：%s", result.summary)
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
        started_at = datetime.now().isoformat(timespec="seconds")
        _set_import_status(
            running=True,
            mode="local",
            last=None,
            started_at=started_at,
            total=0,
            done=0,
            current="",
            percent=0,
            added_n=0,
            updated_n=0,
            skipped_n=0,
            failed_n=0,
            recent=[],
        )
        try:
            result = import_all()
            # 结束时补全计数与百分比；total/done 沿用最后一次进度
            _set_import_status(
                running=False,
                mode="local",
                last=result.to_dict(),
                current="",
                percent=100,
                added_n=len(result.added),
                updated_n=len(result.updated),
                skipped_n=len(result.skipped),
                failed_n=len(result.failed),
                recent=list(result.recent_log[-8:]),
            )
            # 落库，供历史查询
            save_import_log(result, started_at=started_at, mode="local")
        except Exception as exc:  # noqa: BLE001
            _set_import_status(
                running=False,
                mode="local",
                current="",
                last={
                    "added": [],
                    "updated": [],
                    "skipped": [],
                    "failed": [str(exc)],
                    "summary": f"导入失败: {exc}",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        finally:
            _import_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return True


def save_import_log(result: ImportResult, *, started_at: str, mode: str = "local") -> None:
    """把导入结果写入 import_logs；仅记录「新增」，无新增则不落库。"""
    import json as _json

    if not result.added:
        return
    finished = datetime.now().isoformat(timespec="seconds")
    detail = {
        "added": result.added[:500],
    }
    db = SessionLocal()
    try:
        db.add(
            ImportLog(
                started_at=started_at or finished,
                finished_at=finished,
                mode=mode,
                summary=result.summary[:200],
                total=len(result.added) + len(result.updated) + len(result.skipped) + len(result.failed),
                added_n=len(result.added),
                updated_n=len(result.updated),
                skipped_n=len(result.skipped),
                failed_n=len(result.failed),
                detail=_json.dumps(detail, ensure_ascii=False),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def query_import_logs(date: str | None = None, limit: int = 50) -> list[dict]:
    """按日期（YYYY-MM-DD）或最近若干条查询导入历史。"""
    from sqlalchemy import select

    db = SessionLocal()
    try:
        stmt = select(ImportLog).order_by(ImportLog.id.desc()).limit(max(1, min(limit, 200)))
        rows = list(db.execute(stmt).scalars().all())
        out = []
        for r in rows:
            if date and not (r.finished_at or "").startswith(date):
                continue
            d = r.detail_dict
            out.append(
                {
                    "id": r.id,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "mode": r.mode,
                    "summary": r.summary,
                    "total": r.total,
                    "added_n": r.added_n,
                    "updated_n": r.updated_n,
                    "skipped_n": r.skipped_n,
                    "failed_n": r.failed_n,
                    "detail": {
                        "added": d.get("added") or [],
                        "updated": d.get("updated") or [],
                        "skipped": d.get("skipped") or [],
                        "failed": d.get("failed") or [],
                        "recent": d.get("recent") or [],
                    },
                    # 历史只关心新增明细
                    "added_list": d.get("added") or [],
                }
            )
        return out
    finally:
        db.close()


# 供 CLI / 测试使用：确保「书源/分类」文件夹存在
def ensure_category_dirs() -> None:
    settings.novels_dir.mkdir(parents=True, exist_ok=True)
    for src, cats in SOURCE_CATEGORIES.items():
        for c in cats:
            (settings.novels_dir / src / c).mkdir(parents=True, exist_ok=True)
    (settings.novels_dir / UNCATEGORIZED).mkdir(parents=True, exist_ok=True)
