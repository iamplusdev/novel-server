"""Legado WebDAV 进度同步。

生成/读取 Legado「开源阅读」的书籍进度文件 bookProgress/{书名}_{作者}.json，
凭据只保存在服务端环境变量，桌面端不接触 WebDAV 密码。

推送按 durChapterTime 最新者优先，避免覆盖另一台设备写入的更新进度；
写入失败不抛异常（不阻塞桌面阅读），由调用方记录返回值。
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request

from .config import settings

logger = logging.getLogger(__name__)

PROGRESS_DIR = "bookProgress"
_TIMEOUT = 8


def webdav_configured() -> bool:
    return bool(settings.webdav_url and settings.webdav_username and settings.webdav_password)


def _progress_filename(name: str, author: str) -> str:
    """Legado 书籍进度文件名：书名_作者.json（清理文件系统非法字符）"""

    def clean(s: str) -> str:
        return re.sub(r'[\\/:*?"<>|]+', "_", (s or "").strip()) or "未知"

    return f"{clean(name)}_{clean(author)}.json"


def _progress_url(name: str, author: str) -> str:
    root = settings.webdav_url.rstrip("/")
    return f"{root}/{PROGRESS_DIR}/{_progress_filename(name, author)}"


def _request(method: str, url: str, body: bytes | None = None) -> tuple[int, bytes]:
    """极简 WebDAV 请求（PUT/GET/PROPFIND 足够），返回 (状态码, 响应体)。"""
    req = urllib.request.Request(url, data=body, method=method)
    token = base64.b64encode(
        f"{settings.webdav_username}:{settings.webdav_password}".encode("utf-8")
    ).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""


def build_progress_json(
    name: str,
    author: str,
    chapter_index: int,
    chapter_pos: int,
    chapter_time_ms: int,
    chapter_title: str,
) -> bytes:
    """Legado BookProgress 结构（durChapter* 字段与开源阅读互通）。"""
    return json.dumps(
        {
            "name": name,
            "author": author,
            "durChapterIndex": int(chapter_index),
            "durChapterPos": int(chapter_pos),
            "durChapterTime": int(chapter_time_ms),
            "durChapterTitle": chapter_title or "",
        },
        ensure_ascii=False,
    ).encode("utf-8")


def parse_progress(raw: bytes) -> dict | None:
    """解析远端进度；字段缺失/损坏返回 None。"""
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or "durChapterIndex" not in data:
            return None
        return {
            "chapter_index": int(data.get("durChapterIndex") or 0),
            "chapter_pos": int(data.get("durChapterPos") or 0),
            "time": int(data.get("durChapterTime") or 0),
            "chapter_title": str(data.get("durChapterTitle") or ""),
        }
    except Exception:  # noqa: BLE001
        return None


def push_progress(
    name: str,
    author: str,
    chapter_index: int,
    chapter_pos: int,
    chapter_time_ms: int,
    chapter_title: str,
) -> dict:
    """推送进度到 WebDAV；远端时间更新时跳过（最新者优先）。

    返回 {ok, skipped?, reason?}；网络/写入失败 ok=False 且不抛异常。
    """
    if not webdav_configured():
        return {"ok": False, "reason": "webdav_not_configured"}

    url = _progress_url(name, author)
    # 远端已有进度且更新 → 跳过覆盖
    status, raw = _request("GET", url)
    if status == 200:
        remote = parse_progress(raw)
        if remote and remote["time"] > chapter_time_ms:
            return {"ok": True, "skipped": True, "remote": remote}
    # 目标目录可能不存在：先建目录再 PUT（多数 WebDAV 对缺失目录返回 409）
    body = build_progress_json(
        name, author, chapter_index, chapter_pos, chapter_time_ms, chapter_title
    )
    status, _ = _request("PUT", url, body)
    if status in (200, 201, 204):
        return {"ok": True}
    if status == 409:
        parent = url.rsplit("/", 1)[0]
        _request("MKCOL", parent + "/")
        status, _ = _request("PUT", url, body)
        if status in (200, 201, 204):
            return {"ok": True}
    logger.warning("legado push failed: %s %s", status, url)
    return {"ok": False, "reason": f"http_{status}"}


def pull_progress(name: str, author: str) -> dict:
    """拉取远端进度；无进度返回 remote=None。不抛异常。"""
    if not webdav_configured():
        return {"ok": False, "configured": False, "remote": None}
    status, raw = _request("GET", _progress_url(name, author))
    if status != 200:
        return {"ok": True, "configured": True, "remote": None}
    remote = parse_progress(raw)
    return {"ok": True, "configured": True, "remote": remote}
