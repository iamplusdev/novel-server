"""书库体检：重复书合并、损坏 TXT 检测与修复。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .importer import decode_txt_bytes
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


def scan_issues(db: Session) -> list[BookIssue]:
    issues: list[BookIssue] = []
    books = db.execute(select(Book)).scalars().all()
    for book in books:
        chapters = db.execute(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index)
        ).scalars().all()
        if not chapters:
            issues.append(BookIssue(book.id, book.title, "empty_chapters", "没有任何章节"))
            continue

        total_len = sum(len(c.content or "") for c in chapters)
        # 大体量却只有 1 章 → 多半章节标题没识别
        if book.word_count >= 5000 and len(chapters) <= 1:
            issues.append(
                BookIssue(
                    book.id,
                    book.title,
                    "chapter_parse",
                    f"疑似未分章（仅 {len(chapters)} 章 / {book.word_count} 字）",
                    {"chapter_count": len(chapters), "word_count": book.word_count},
                )
            )

        joined = "\n".join(c.content or "" for c in chapters)
        repl = joined.count("�")
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
        ctrl = len(_CTRL_RE.findall(joined))
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

        empty_n = sum(1 for c in chapters if not (c.content or "").strip())
        if empty_n and empty_n >= max(1, len(chapters) // 3):
            issues.append(
                BookIssue(
                    book.id,
                    book.title,
                    "empty_chapters",
                    f"空章节 {empty_n}/{len(chapters)}",
                    {"empty": empty_n, "total": len(chapters)},
                )
            )

        # 源文件是否还在（便于重解析）
        if book.source_path:
            if book.source_path.startswith("webdav:"):
                pass  # WebDAV 源运行时再查
            else:
                p = Path(book.source_path)
                if not p.is_file():
                    issues.append(
                        BookIssue(book.id, book.title, "source_missing", "源 TXT 不在原路径，无法自动重解析")
                    )
        if total_len == 0:
            issues.append(BookIssue(book.id, book.title, "empty_chapters", "正文全部为空"))
    return issues


def find_duplicate_groups(db: Session) -> list[dict]:
    rows = db.execute(
        select(Book.title, Book.author, func.count(Book.id).label("n"))
        .group_by(Book.title, Book.author)
        .having(func.count(Book.id) > 1)
    ).all()
    groups = []
    for title, author, n in rows:
        books = db.execute(
            select(Book)
            .where(Book.title == title, Book.author == author)
            .order_by(Book.chapter_count.desc(), Book.word_count.desc(), Book.id.asc())
        ).scalars().all()
        groups.append({
            "title": title,
            "author": author,
            "count": n,
            "keep_id": books[0].id,
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
    for bid in delete_ids:
        book = db.get(Book, bid)
        if not book:
            continue
        if book.title != keep.title or book.author != keep.author:
            raise ValueError(f"《{book.title}》与保留项书名/作者不一致，已中止")
        if book.cover_file and not keep.cover_file:
            keep.cover_file = book.cover_file  # 迁移封面
            book.cover_file = ""
        if book.source and not keep.source:
            keep.source = book.source
            keep.source_id = book.source_id
        deleted.append({"id": book.id, "title": book.title, "source_path": book.source_path})
        if book.cover_file:
            p = settings.covers_dir / book.cover_file
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        db.delete(book)

    keep.updated_at = datetime.now().isoformat(timespec="seconds")
    db.commit()
    return {"kept": {"id": keep.id, "title": keep.title}, "deleted": deleted}


def _read_source_text(book: Book) -> str | None:
    """读取源 TXT 文本（本地路径或 webdav:）。失败返回 None。"""
    sp = book.source_path or ""
    if sp.startswith("webdav:"):
        rel = sp[len("webdav:") :].lstrip("/")
        try:
            from .backup import load_config
            from .webdav import WebDAVClient

            cfg = load_config()
            if not cfg.webdav_url:
                return None
            client = WebDAVClient(cfg.webdav_url, cfg.username, cfg.password, timeout=120)
            raw = client.get_file(rel)
            return decode_txt_bytes(raw)
        except Exception:  # noqa: BLE001
            return None
    p = Path(sp)
    if not sp or not p.is_file():
        return None
    try:
        return decode_txt_bytes(p.read_bytes())
    except OSError:
        return None


def _best_decode(raw: bytes) -> str:
    """优先选无替换符的编码。"""
    best = ""
    best_score = -1
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16", "utf-16-le"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        score = -text.count("�") * 100 + len(text)
        if text.startswith("﻿"):
            score += 5
        if score > best_score:
            best_score = score
            best = text
    return best or raw.decode("utf-8", errors="replace")


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
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index)
    ).scalars().all()
    actions = []

    # 1) 清理字符
    if mode in ("clean", "auto", "reparse"):
        changed = False
        for ch in chapters:
            raw = ch.content or ""
            cleaned = _clean_text(raw)
            if cleaned != raw:
                ch.content = cleaned
                changed = True
        if changed:
            actions.append("已清理控制字符/零宽字符")

    need_reparse = mode == "reparse"
    if mode == "auto":
        need_reparse = (
            book.word_count >= 5000 and len(chapters) <= 1
        ) or any((c.content or "").count("�") >= 5 for c in chapters) or not chapters

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
                db.query(Chapter).filter(Chapter.book_id == book.id).delete()
                for i, ch in enumerate(parsed.chapters):
                    db.add(
                        Chapter(
                            book_id=book.id,
                            index=i,
                            title=re.sub(r"\s+", " ", ch.title).strip()[:200],
                            content=_clean_text(ch.content),
                        )
                    )
                book.chapter_count = len(parsed.chapters)
                book.word_count = sum(len(c.content) for c in parsed.chapters)
                book.latest_chapter = parsed.chapters[-1].title[:200] if parsed.chapters else ""
                if not book.intro and parsed.intro:
                    book.intro = parsed.intro
                actions.append(f"已从源重新解析为 {len(parsed.chapters)} 章")

    # 刷新统计
    chapters = db.execute(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index)
    ).scalars().all()
    book.chapter_count = len(chapters)
    book.word_count = sum(len(c.content or "") for c in chapters)
    if chapters:
        book.latest_chapter = chapters[-1].title[:200]
    book.updated_at = datetime.now().isoformat(timespec="seconds")
    db.commit()

    return {
        "id": book.id,
        "title": book.title,
        "actions": actions or ["无需修复"],
        "chapter_count": book.chapter_count,
        "word_count": book.word_count,
    }


def repair_books(db: Session, book_ids: list[int] | None = None, mode: str = "auto") -> list[dict]:
    if book_ids is None:
        book_ids = [i.book_id for i in scan_issues(db)]
        book_ids = list(dict.fromkeys(book_ids))
    results = []
    for bid in book_ids:
        try:
            results.append(repair_book(db, bid, mode=mode))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": bid, "title": "", "actions": [f"失败: {exc}"]})
    return results
