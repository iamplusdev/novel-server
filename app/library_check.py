"""书库体检：重复书合并、损坏 TXT 检测与修复。"""
from __future__ import annotations

import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from .config import category_rel_parts, safe_delete_cover, settings
from .content_store import commit_pack, discard_pack, read_book_texts, write_pack_staged
from .database import delete_books_safe
from .importer import UNCATEGORIZED, decode_txt_bytes
from .models import Book, Chapter
from .parsers import load_txt_book_from_text

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REPL_RE = re.compile("�")


@dataclass
class BookIssue:
    book_id: int
    title: str
    kind: str  # chapter_parse | encoding | control_chars | empty_chapters | source_missing
    message: str
    detail: dict = field(default_factory=dict)


def _clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _CTRL_RE.sub("", s)
    s = re.sub(r"[​‌‍﻿ ]", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def _load_chapter_texts(db: Session, book_id: int, chapters) -> list[str]:
    """读各章正文：优先正文包偏移，回退遗留 content 列。"""
    spans = [(c.content_offset or 0, c.content_length or 0) for c in chapters]
    texts = read_book_texts(book_id, spans)
    # 迁移前旧数据：偏移为空时用 content 列
    return [t or (c.content or "") for t, c in zip(texts, chapters)]


def scan_issues(
    db: Session,
    deep: bool = False,
    on_progress=None,
    cancel: threading.Event | None = None,
) -> list[BookIssue]:
    """体检扫描（分批处理，避免一次性加载整库）。

    deep=False（默认，快速）：仅 SQL 聚合 + 源文件存在性，不读正文。
    deep=True（深度）：额外读正文包检查乱码/控制字符，大库较慢。
    on_progress(done, total) 可选，供后台任务展示进度；cancel 可中止。
    """
    issues: list[BookIssue] = []
    total = db.execute(select(func.count(Book.id))).scalar_one()
    page_size = 500
    last_id = 0
    done = 0
    while True:
        if cancel is not None and cancel.is_set():
            break
        books = db.execute(
            select(Book).where(Book.id > last_id).order_by(Book.id).limit(page_size)
        ).scalars().all()
        if not books:
            break
        last_id = books[-1].id
        _scan_books(db, books, deep, issues)
        done += len(books)
        if on_progress is not None:
            on_progress(min(done, total), total)
    return issues


def _scan_books(db: Session, books, deep: bool, issues: list[BookIssue]) -> None:
    """扫描一批书：先做章节聚合（不读正文），deep 时再按书读正文包查乱码/控制符。"""
    ids = [b.id for b in books]
    # 章节级聚合：数量 / 总字数 / 空章（不加载正文）
    stats_rows = db.execute(
        select(
            Chapter.book_id,
            func.count(Chapter.id).label("n"),
            func.coalesce(func.sum(Chapter.content_chars), 0).label("total_len"),
            func.coalesce(
                func.sum(case((Chapter.content_chars == 0, 1), else_=0)), 0
            ).label("empty_n"),
        ).where(Chapter.book_id.in_(ids)).group_by(Chapter.book_id)
    ).all()
    stats = {
        r.book_id: {"n": r.n, "total_len": r.total_len, "empty_n": r.empty_n}
        for r in stats_rows
    }

    # 控制字符 / 乱码：仅深度体检时按书读正文包；按批次取偏移元数据，避免整库进内存
    ctrl_counts: dict[int, int] = {}
    repl_counts: dict[int, int] = {}
    if deep:
        rows = db.execute(
            select(
                Chapter.book_id,
                Chapter.content_offset,
                Chapter.content_length,
                Chapter.content,
            ).where(Chapter.book_id.in_(ids)).order_by(Chapter.book_id, Chapter.index, Chapter.id)
        ).all()
        chapters_by_book: dict[int, list] = {}
        for r in rows:
            chapters_by_book.setdefault(r.book_id, []).append(r)
        for book in books:
            ch_rows = chapters_by_book.get(book.id) or []
            if not ch_rows:
                continue

            class _Ch:
                pass

            stubs = []
            for r in ch_rows:
                s = _Ch()
                s.content_offset = r.content_offset or 0
                s.content_length = r.content_length or 0
                s.content = r.content or ""
                stubs.append(s)
            for text in _load_chapter_texts(db, book.id, stubs):
                if not text:
                    continue
                n_ctrl = len(_CTRL_RE.findall(text))
                if n_ctrl:
                    ctrl_counts[book.id] = ctrl_counts.get(book.id, 0) + n_ctrl
                n_repl = text.count("\ufffd")
                if n_repl:
                    repl_counts[book.id] = repl_counts.get(book.id, 0) + n_repl

    for book in books:
        _issues_for_book(book, stats.get(book.id), ctrl_counts, repl_counts, issues)


def _issues_for_book(book, st, ctrl_counts, repl_counts, issues: list[BookIssue]) -> None:
    """依据聚合统计为单本书汇总问题明细。"""
    if not st or st["n"] == 0:
        issues.append(BookIssue(book.id, book.title, "empty_chapters", "没有任何章节"))
        return

    total_len = st["total_len"] or 0
    # 大体量却只有 1 章 → 多半章节标题没识别
    if book.word_count >= 5000 and st["n"] <= 1:
        issues.append(
            BookIssue(
                book.id,
                book.title,
                "chapter_parse",
                f"疑似未分章（仅 {st['n']} 章 / {book.word_count} 字）",
                {"chapter_count": st["n"], "word_count": book.word_count},
            )
        )

    repl = repl_counts.get(book.id, 0)
    if repl >= 5:
        issues.append(
            BookIssue(
                book.id,
                book.title,
                "encoding",
                f"存在乱码替换符 ×{repl}（可能编码识别错误）",
                {"replacements": repl},
            )
        )
    ctrl = ctrl_counts.get(book.id, 0)
    if ctrl >= 10:
        issues.append(
            BookIssue(
                book.id,
                book.title,
                "control_chars",
                f"含控制字符 ×{ctrl}（可清理）",
                {"count": ctrl},
            )
        )

    empty_n = st["empty_n"] or 0
    if empty_n and empty_n >= max(1, st["n"] // 3):
        issues.append(
            BookIssue(
                book.id,
                book.title,
                "empty_chapters",
                f"空章节 {empty_n}/{st['n']}",
                {"empty": empty_n, "total": st["n"]},
            )
        )

    # 源文件是否还在（便于重解析）
    if book.source_path and not book.source_path.startswith("webdav:"):
        if not Path(book.source_path).is_file():
            issues.append(
                BookIssue(book.id, book.title, "source_missing", "源 TXT 不在原路径，无法自动重解析")
            )
    if total_len == 0:
        issues.append(BookIssue(book.id, book.title, "empty_chapters", "正文全部为空"))


_DUP_STRIP_RE = re.compile(r"[《》〈〉\[\]【】()（）\s·:：\-—・]")
_DUP_SUFFIX_RE = re.compile(r"(校对版全本|校对版|精校版|全本|修订版|未删节版|未删节|实体书|完本)")


def _norm_dup(s: str) -> str:
    """重复检测归一化：去掉书名号/括号/空白/常见版本后缀，容忍近似书名。"""
    s = _DUP_SUFFIX_RE.sub("", s or "")
    return _DUP_STRIP_RE.sub("", s).lower()


def find_duplicate_groups(db: Session) -> list[dict]:
    """按“归一化书名+作者”找出重复书（容忍书名号/空白/校对版等差异）。

    只投影必要列，避免把 intro 等大字段读进内存。
    """
    rows = db.execute(
        select(
            Book.id,
            Book.title,
            Book.author,
            Book.chapter_count,
            Book.word_count,
            Book.source_path,
            Book.source,
            Book.source_id,
            Book.cover_file,
        )
    ).all()
    buckets: dict[tuple[str, str], list] = {}
    for r in rows:
        buckets.setdefault((_norm_dup(r.title), _norm_dup(r.author)), []).append(r)

    groups = []
    for books in buckets.values():
        if len(books) < 2:
            continue
        # 保留章节/字数最多的那本（与原行为一致）
        books.sort(key=lambda b: (-(b.chapter_count or 0), -(b.word_count or 0), b.id))
        keep = books[0]
        groups.append({
            "title": keep.title,
            "author": keep.author,
            "count": len(books),
            "keep_id": keep.id,
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
    groups.sort(key=lambda g: (-g["count"], g["title"]))
    return groups


def merge_duplicates(db: Session, keep_id: int, delete_ids: list[int]) -> dict:
    """保留 keep_id，删除其余重复书（章节/封面一并删）。"""
    if keep_id in delete_ids:
        raise ValueError("保留 ID 不能出现在删除列表中")
    if not delete_ids:
        raise ValueError("没有要删除的书")

    keep = db.get(Book, keep_id)
    if not keep:
        raise ValueError(f"保留的书不存在: {keep_id}")

    deleted = []
    to_delete: list[int] = []
    for bid in delete_ids:
        book = db.get(Book, bid)
        if not book:
            continue
        if _norm_dup(book.title) != _norm_dup(keep.title) or _norm_dup(book.author) != _norm_dup(
            keep.author
        ):
            raise ValueError(f"《{book.title}》与保留项书名/作者不一致，已中止")
        cover_name = book.cover_file
        if book.source and not keep.source:
            keep.source = book.source
            keep.source_id = book.source_id
        deleted.append({"id": book.id, "title": book.title, "source_path": book.source_path})
        # 封面优先迁移给保留项，否则删封面图（源 TXT 永不删除）
        if cover_name and not keep.cover_file:
            keep.cover_file = cover_name
        elif cover_name:
            safe_delete_cover(cover_name)
        to_delete.append(book.id)

    keep.updated_at = datetime.now().isoformat(timespec="seconds")
    # 先提交保留项修改，避免删除失败回滚时丢掉封面迁移/来源补全
    db.commit()
    try:
        # 批量删章节+书籍；FTS 触发器失败时自动重建索引
        delete_books_safe(db, to_delete)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"删除失败：{e}") from e
    return {"kept": {"id": keep.id, "title": keep.title}, "deleted": deleted}


def _read_source_text(book: Book) -> str | None:
    """读取本地源 TXT 文本。失败返回 None。"""
    sp = book.source_path or ""
    # WebDAV 备份已移除，历史 webdav: 路径无法再读取
    if sp.startswith("webdav:"):
        return None
    p = Path(sp)
    if not sp or not p.is_file():
        return None
    try:
        return decode_txt_bytes(p.read_bytes())
    except OSError:
        return None


def repair_book(db: Session, book_id: int, mode: str = "auto") -> dict:
    """修复一本书。

    mode:
      - clean: 仅清理控制字符/零宽
      - reparse: 从源文件重新解析章节（需源文件）
      - auto: 有问题则重解析；无源则 clean
    """
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("书籍不存在")

    chapters = db.execute(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index, Chapter.id)
    ).scalars().all()
    actions = []
    texts = _load_chapter_texts(db, book.id, chapters)
    staged = False  # 是否已把新正文写入临时包（决定提交/回滚时切换或丢弃）

    # 1) 清理字符（读正文包 → 清理后整包重写并回填偏移）
    if mode in ("clean", "auto", "reparse"):
        cleaned_list = [_clean_text(t or "") for t in texts]
        if cleaned_list != texts:
            spans = write_pack_staged(book.id, cleaned_list)
            staged = True
            for ch, txt, (off, blen, clen) in zip(chapters, cleaned_list, spans):
                ch.content = ""
                ch.content_offset = off
                ch.content_length = blen
                ch.content_chars = clen
            texts = cleaned_list
            actions.append("已清理控制字符/零宽字符")

    need_reparse = mode == "reparse"
    if mode == "auto":
        need_reparse = (
            book.word_count >= 5000 and len(chapters) <= 1
        ) or any((t or "").count("�") >= 5 for t in texts) or not chapters

    if need_reparse:
        src = _read_source_text(book)
        if not src:
            actions.append("无法读取源 TXT，仅做了字符清理")
        else:
            # 再按最佳编码（decode_txt_bytes 已试过，这里对 bytes 重新选择）
            parsed = load_txt_book_from_text(src, Path(book.source_path or book.title).stem, book.category)
            if len(parsed.chapters) <= 1 and len(chapters) > 1:
                actions.append("源文件仍无法分章，保留原章节结构")
            else:
                db.execute(delete(Chapter).where(Chapter.book_id == book.id))
                cleaned = [_clean_text(ch.content) for ch in parsed.chapters]
                spans = write_pack_staged(book.id, cleaned)
                staged = True
                rows = []
                for i, (ch, txt, (off, blen, clen)) in enumerate(
                    zip(parsed.chapters, cleaned, spans)
                ):
                    rows.append(
                        {
                            "book_id": book.id,
                            "index": i,
                            "title": re.sub(r"\s+", " ", ch.title).strip()[:200],
                            "content": "",
                            "content_offset": off,
                            "content_length": blen,
                            "content_chars": clen,
                        }
                    )
                if rows:
                    from sqlalchemy import insert as sa_insert

                    db.execute(sa_insert(Chapter), rows)
                book.chapter_count = len(parsed.chapters)
                book.word_count = sum(len(t) for t in cleaned)
                book.latest_chapter = parsed.chapters[-1].title[:200] if parsed.chapters else ""
                if not book.intro and parsed.intro:
                    book.intro = parsed.intro
                actions.append(f"已从源重新解析为 {len(parsed.chapters)} 章")

    # 刷新统计（字数用正文字符数）
    chapters = db.execute(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index, Chapter.id)
    ).scalars().all()
    book.chapter_count = len(chapters)
    book.word_count = sum(c.content_chars or len(c.content or "") for c in chapters)
    if chapters:
        book.latest_chapter = chapters[-1].title[:200]
    book.updated_at = datetime.now().isoformat(timespec="seconds")
    # DB 提交成功后再切换正文包；失败回滚并丢弃临时包，避免偏移与正文不一致
    try:
        db.commit()
    except Exception:
        db.rollback()
        if staged:
            discard_pack(book.id)
        raise
    if staged:
        commit_pack(book.id)

    return {
        "id": book.id,
        "title": book.title,
        "actions": actions or ["无需修复"],
        "chapter_count": book.chapter_count,
        "word_count": book.word_count,
    }


def repair_books(db: Session, book_ids: list[int] | None = None, mode: str = "auto") -> list[dict]:
    if book_ids is None:
        # 未指定书目时做深度扫描以覆盖乱码/控制符问题
        book_ids = [i.book_id for i in scan_issues(db, deep=True)]
        book_ids = list(dict.fromkeys(book_ids))
    results = []
    for bid in book_ids:
        try:
            results.append(repair_book(db, bid, mode=mode))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": bid, "title": "", "actions": [f"失败: {exc}"]})
    return results


def relocate_book(book: Book) -> dict:
    """把本地源 TXT 归位到 novels/<书源>/<分类>/。

    只移动文件位置并回写 source_path，不改章节内容。
    目标层级 = category_rel_parts(book.category)。
    """
    target = (book.category or "").strip() or UNCATEGORIZED
    parts = category_rel_parts(target)
    target_disp = "/".join(parts)
    sp = book.source_path or ""
    actions: list[str] = []
    failed: list[str] = []

    # WebDAV 已移除，仅处理本地路径
    if sp.startswith("webdav:"):
        failed.append("WebDAV 源路径已不支持")
    elif not sp:
        failed.append("缺少源路径")
    else:
        local_src = Path(sp)
        if not local_src.is_file():
            failed.append("本地源文件不存在")
        else:
            dest_dir = settings.novels_dir.joinpath(*parts)
            try:
                if local_src.parent.resolve() == dest_dir.resolve():
                    actions.append(f"本地已在 {target_disp}/")
                else:
                    dest = dest_dir / local_src.name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if dest.exists() and dest.resolve() != local_src.resolve():
                        dest = dest_dir / f"{local_src.stem}_{book.id}{local_src.suffix}"
                    # shutil.move 支持跨盘（Path.replace 仅同盘原子）
                    shutil.move(str(local_src), str(dest))
                    actions.append(f"本地 → {target_disp}/{dest.name}")
                    book.source_path = str(dest)
            except OSError as e:
                failed.append(f"本地移动失败: {e}")

    ok = bool(actions) and not failed
    return {
        "id": book.id,
        "title": book.title,
        "category": target_disp,
        "source_path": book.source_path,
        "actions": actions,
        "failed": failed,
        "ok": ok,
    }


def relocate_books(db: Session, book_ids: list[int] | None = None) -> dict:
    """批量按分类归位。book_ids 为空则处理全库。"""
    if book_ids is None:
        books = db.execute(select(Book).order_by(Book.id)).scalars().all()
    else:
        books = [b for bid in book_ids if (b := db.get(Book, bid)) is not None]

    results = []
    for book in books:
        try:
            results.append(relocate_book(book))
        except Exception as exc:  # noqa: BLE001
            results.append({
                "id": book.id,
                "title": book.title,
                "category": book.category,
                "source_path": book.source_path,
                "actions": [],
                "failed": [str(exc)],
                "ok": False,
            })
    db.commit()
    moved = sum(1 for r in results if any("→" in a for a in r.get("actions") or []))
    failed_n = sum(1 for r in results if r.get("failed"))
    return {
        "results": results,
        "count": len(results),
        "moved": moved,
        "failed": failed_n,
    }


# ---------------------------------------------------------------------------
# 后台体检任务：深度扫描耗时较长，改为后台线程 + 进度轮询/SSE，前端不阻塞、可取消
# ---------------------------------------------------------------------------
_scan_lock = threading.Lock()
_scan_status_lock = threading.Lock()
_scan_cancel = threading.Event()
_scan_status: dict = {
    "running": False,
    "deep": False,
    "total": 0,
    "done": 0,
    "percent": 0,
    "error": "",
    "report": None,
}


def _set_scan_status(**fields) -> None:
    global _scan_status
    with _scan_status_lock:
        _scan_status = {**_scan_status, **fields}


def get_scan_status() -> dict:
    with _scan_status_lock:
        return dict(_scan_status)


def request_scan_cancel() -> bool:
    """请求中止后台体检；运行中才有效。"""
    if not _scan_status.get("running"):
        return False
    _scan_cancel.set()
    return True


def run_library_scan(deep: bool = False) -> dict:
    """执行一次体检（重复 + 异常），返回报告 dict；供后台任务调用。"""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        dups = find_duplicate_groups(db)
        issues = scan_issues(
            db,
            deep=deep,
            on_progress=lambda done, total: _set_scan_status(
                done=done,
                total=total,
                percent=int(done * 100 / total) if total else 0,
            ),
            cancel=_scan_cancel,
        )
        return {
            "duplicates": dups,
            "issues": [
                {
                    "book_id": i.book_id,
                    "title": i.title,
                    "kind": i.kind,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in issues
            ],
            "duplicate_groups": len(dups),
            "issue_count": len(issues),
            "deep": deep,
        }
    finally:
        db.close()


def start_library_scan(deep: bool = False) -> bool:
    """后台线程执行体检；已有任务在跑返回 False。"""
    from .task_guard import other_task_running

    if not _scan_lock.acquire(blocking=False):
        return False
    # 与导入/刮削互斥：其它长任务在跑时不启动
    if _scan_status.get("running") or other_task_running("scan"):
        _scan_lock.release()
        return False
    _scan_cancel.clear()

    def _run() -> None:
        _set_scan_status(
            running=True, deep=deep, total=0, done=0, percent=0, error="", report=None
        )
        try:
            report = run_library_scan(deep)
            _set_scan_status(running=False, percent=100, report=report)
        except Exception as exc:  # noqa: BLE001
            _set_scan_status(running=False, error=str(exc))
        finally:
            _scan_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return True
