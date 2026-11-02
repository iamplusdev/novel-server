"""与 Legado（开源阅读）互通的阅读进度同步。

Legado 的进度文件：{WebDAV}/{dir}/bookProgress/{书名}_{作者}.json
字段：name / author / durChapterIndex / durChapterPos / durChapterTime / durChapterTitle
- durChapterIndex 为 0 基章节序号
- durChapterPos 为章内字符位置
- durChapterTime 为毫秒时间戳
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import webdav_settings
from .models import Book, Chapter
from .webdav import WebDavClient, WebDavError

logger = logging.getLogger("sync")

# Legado 的 normalizeFileName：把非法文件名字符替换为下划线
_BAD_FILENAME = re.compile(r'[\\/:*?"<>|]')


def progress_filename(name: str, author: str) -> str:
    """生成与 Legado 一致的文件名（URL 编码后的 {书名}_{作者}.json）。"""
    safe = _BAD_FILENAME.sub("_", f"{name or ''}_{author or ''}")
    return quote(safe, safe="") + ".json"


def _dir_url(base_url: str, dir_name: str) -> str:
    segs = [quote(p, safe="") for p in (dir_name or "").split("/") if p]
    base = (base_url or "").rstrip("/")
    return f"{base}/{'/'.join(segs)}" if segs else base


def progress_dir_url(settings: dict) -> str:
    return f"{_dir_url(settings['url'], settings['dir'])}/bookProgress/"


def progress_url(settings: dict, filename: str) -> str:
    return f"{progress_dir_url(settings)}{filename}"


def _mkcol_chain(client: WebDavClient, settings: dict) -> None:
    """逐级创建目录（支持 dir 含多级路径），再创建 bookProgress。"""
    current = (settings["url"] or "").rstrip("/")
    for seg in [p for p in (settings["dir"] or "").split("/") if p]:
        current += "/" + quote(seg, safe="")
        client.mkcol(current)
    client.mkcol(f"{current}/bookProgress")


def _client(settings: dict) -> WebDavClient:
    return WebDavClient(
        base_url=settings["url"],
        username=settings["username"],
        password=settings["password"],
        timeout=float(settings["timeout"]),
        verify_tls=bool(settings.get("verify_tls", True)),
    )


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_remote(raw: bytes) -> dict | None:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "name": str(data.get("name") or ""),
        "author": str(data.get("author") or ""),
        "durChapterIndex": _to_int(data.get("durChapterIndex"), -1),
        "durChapterPos": max(0, _to_int(data.get("durChapterPos"), 0)),
        "durChapterTime": max(0, _to_int(data.get("durChapterTime"), 0)),
        "durChapterTitle": str(data.get("durChapterTitle") or ""),
    }


def _iso_to_ms(value: str) -> int:
    try:
        return int(datetime.fromisoformat(value or "").timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def _ms_to_iso(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return datetime.now().isoformat(timespec="seconds")


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", "", (title or "")).lower()


def resolve_chapter(chapters: list[Chapter], remote: dict) -> Chapter | None:
    """章节匹配：标题优先，序号兜底（Legado 与本地章节顺序可能不同）。"""
    idx = int(remote.get("durChapterIndex", -1))
    title = _norm_title(str(remote.get("durChapterTitle") or ""))
    if title:
        matches = [c for c in chapters if _norm_title(c.title) == title]
        if matches:
            if 0 <= idx < len(chapters):
                return min(matches, key=lambda c: abs(c.index - idx))
            return matches[0]
    if 0 <= idx < len(chapters):
        return chapters[idx]
    return None


def _chapters(db: Session, book_id: int) -> list[Chapter]:
    return (
        db.execute(
            select(Chapter)
            .where(Chapter.book_id == book_id)
            .order_by(Chapter.index, Chapter.id)
        )
        .scalars()
        .all()
    )


def pull_progress(db: Session, book_id: int) -> dict:
    """打开阅读页时拉取远端进度；远端更新则写入本地并返回目标章节。"""
    settings = webdav_settings.load()
    if not webdav_settings.is_configured(settings):
        return {"enabled": False, "updated": False}

    book = db.get(Book, book_id)
    if book is None:
        raise ValueError("书籍不存在")

    filename = progress_filename(book.title, book.author)
    try:
        raw = _client(settings).get(progress_url(settings, filename))
    except Exception as exc:  # noqa: BLE001
        # 网络/证书/URL 异常统一降级为「本次不更新」，不阻断阅读
        logger.warning("拉取远程进度失败 book=%s: %s", book_id, exc)
        return {
            "enabled": True,
            "found": False,
            "updated": False,
            "filename": filename,
            "error": str(exc),
        }

    if raw is None:
        return {"enabled": True, "found": False, "updated": False, "filename": filename}

    remote = _parse_remote(raw)
    if remote is None:
        return {
            "enabled": True,
            "found": True,
            "updated": False,
            "filename": filename,
            "error": "远端进度格式无法识别",
        }

    chapters = _chapters(db, book_id)
    chapter = resolve_chapter(chapters, remote)
    base = {
        "enabled": True,
        "found": True,
        "filename": filename,
        "remote_chapter_index": remote["durChapterIndex"],
        "remote_chapter_title": remote["durChapterTitle"],
        "remote_time": remote["durChapterTime"],
    }
    if chapter is None:
        return {**base, "updated": False, "error": "无法匹配本地章节"}

    remote_ms = remote["durChapterTime"]
    local_ms = _iso_to_ms(book.read_at)
    if remote_ms and local_ms and remote_ms <= local_ms:
        return {
            **base,
            "updated": False,
            "reason": "本地进度更新",
            "chapter_id": chapter.id,
            "chapter_index": chapter.index,
        }
    if not remote_ms:
        # 没有时间戳时只允许向前，避免无依据回退
        if remote["durChapterIndex"] <= book.read_chapter_index:
            return {
                **base,
                "updated": False,
                "reason": "远端无时间戳且未前进",
                "chapter_id": chapter.id,
                "chapter_index": chapter.index,
            }
        remote_ms = int(time.time() * 1000)

    total = len(chapters)
    book.read_chapter_index = int(chapter.index)
    book.read_percent = int(round((chapter.index + 1) * 100 / total)) if total else 0
    book.read_at = _ms_to_iso(remote_ms)
    db.commit()

    return {
        **base,
        "updated": True,
        "chapter_id": chapter.id,
        "chapter_index": chapter.index,
        "chapter_title": chapter.title,
        "chapter_pos": remote["durChapterPos"],
    }


def _build_payload(book: Book, chapter: Chapter, pos: int, time_ms: int) -> dict:
    return {
        "name": book.title,
        "author": book.author,
        "durChapterIndex": int(chapter.index),
        "durChapterPos": max(0, int(pos)),
        "durChapterTime": int(time_ms),
        "durChapterTitle": chapter.title or "",
    }


def push_progress(
    db: Session,
    book_id: int,
    chapter_id: int,
    chapter_pos: int = 0,
    time_ms: int | None = None,
) -> dict:
    """把当前进度写入 Legado 的 bookProgress 文件。

    写入前先读远端：若远端时间明显更新（另一台设备刚读过），跳过本次写入。
    """
    settings = webdav_settings.load()
    if not webdav_settings.is_configured(settings):
        return {"enabled": False, "pushed": False}

    book = db.get(Book, book_id)
    chapter = db.get(Chapter, chapter_id)
    if book is None or chapter is None or chapter.book_id != book_id:
        raise ValueError("书籍或章节不存在")

    filename = progress_filename(book.title, book.author)
    url = progress_url(settings, filename)
    # 客户端时钟偏差过大时以服务端时间为准（±5 分钟内才信任）
    server_ms = int(time.time() * 1000)
    now_ms = (
        int(time_ms)
        if time_ms and abs(int(time_ms) - server_ms) <= 5 * 60 * 1000
        else server_ms
    )

    try:
        client = _client(settings)
        try:
            raw = client.get(url)
            remote = _parse_remote(raw) if raw else None
            if remote and remote["durChapterTime"] > now_ms + 2000:
                return {
                    "enabled": True,
                    "pushed": False,
                    "skipped": "remote_newer",
                    "filename": filename,
                    "remote_time": remote["durChapterTime"],
                }
        except WebDavError:
            # 读不到远端时仍尝试写入（例如文件尚不存在）
            pass

        _mkcol_chain(client, settings)
        payload = _build_payload(book, chapter, chapter_pos, now_ms)
        client.put(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return {
            "enabled": True,
            "pushed": True,
            "filename": filename,
            "remote_time": now_ms,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("推送远程进度失败 book=%s: %s", book_id, exc)
        return {"enabled": True, "pushed": False, "filename": filename, "error": str(exc)}


def push_progress_bg(
    book_id: int,
    chapter_id: int,
    chapter_pos: int = 0,
    time_ms: int | None = None,
) -> None:
    """后台线程推送（供关闭页面/Beacon 使用），不阻塞请求。"""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        push_progress(db, book_id, chapter_id, chapter_pos, time_ms)
    except Exception:  # noqa: BLE001
        logger.exception("后台推送进度失败 book=%s", book_id)
    finally:
        db.close()


def sync_info(db: Session, book_id: int) -> dict:
    """详情页诊断：本地进度、远程文件是否存在、远端进度与章节匹配结果。"""
    settings = webdav_settings.load()
    book = db.get(Book, book_id)
    if book is None:
        raise ValueError("书籍不存在")

    filename = progress_filename(book.title, book.author)
    info: dict = {
        "enabled": bool(settings["enabled"]),
        "configured": webdav_settings.is_configured(settings),
        "filename": filename,
        "url": progress_url(settings, filename) if settings.get("url") else "",
        "local": {
            "read_chapter_index": int(book.read_chapter_index),
            "read_percent": int(book.read_percent),
            "read_at": book.read_at or "",
        },
        "remote_exists": False,
        "remote": None,
        "matched": None,
        "error": "",
    }
    if not info["configured"]:
        info["error"] = "尚未启用 WebDAV（或未填写地址）" if not settings["enabled"] else "未填写 WebDAV 地址"
        return info

    try:
        raw = _client(settings).get(progress_url(settings, filename))
        if raw is None:
            return info
        info["remote_exists"] = True
        remote = _parse_remote(raw)
        info["remote"] = remote
        if remote is None:
            info["error"] = "远端进度格式无法识别"
            return info
        chapters = _chapters(db, book_id)
        chapter = resolve_chapter(chapters, remote)
        if chapter is None:
            info["error"] = "无法匹配本地章节（标题与序号均未命中）"
        else:
            info["matched"] = {
                "chapter_id": chapter.id,
                "index": chapter.index,
                "title": chapter.title,
            }
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    return info


def push_now(book_id: int, chapter_id: int | None = None) -> dict:
    """手动推送当前本地进度（按钮触发，同步返回结果）。"""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            raise ValueError("书籍不存在")
        chapter: Chapter | None = None
        if chapter_id:
            chapter = db.get(Chapter, chapter_id)
            if chapter is None or chapter.book_id != book_id:
                raise ValueError("章节不存在")
        else:
            chapter = (
                db.execute(
                    select(Chapter)
                    .where(
                        Chapter.book_id == book_id,
                        Chapter.index == int(book.read_chapter_index),
                    )
                    .order_by(Chapter.id)
                )
                .scalars()
                .first()
            )
        if chapter is None:
            return {"enabled": True, "pushed": False, "error": "本地还没有阅读进度"}
        last_ms = _iso_to_ms(book.read_at) or int(time.time() * 1000)
        return push_progress(db, book_id, chapter.id, 0, last_ms)
    finally:
        db.close()


def test_connection() -> dict:
    """测试 WebDAV 连接，并尝试创建 legado/bookProgress 目录。"""
    settings = webdav_settings.load()
    if not settings.get("url"):
        raise ValueError("请先填写 WebDAV 地址")
    client = _client(settings)
    root = _dir_url(settings["url"], settings["dir"])
    try:
        if not client.propfind(root):
            client.mkcol(root)
        _mkcol_chain(client, settings)
        return {"ok": True, "message": "连接成功", "root": root}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "root": root}
