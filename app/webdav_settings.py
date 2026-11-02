"""WebDAV 进度同步配置：data/webdav_settings.json（密码只写不读）。

配置由管理端保存；接口只返回 has_password，不回传明文。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .config import settings

FILE_NAME = "webdav_settings.json"
_LOCK = threading.Lock()

DEFAULTS: dict = {
    "enabled": False,
    "url": "",
    "username": "",
    "password": "",
    "dir": "legado",
    "timeout": 6,
    "verify_tls": True,
}


def config_path() -> Path:
    parent = settings.database_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent / FILE_NAME


def _clean_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("WebDAV 地址需以 http:// 或 https:// 开头")
    return value


def _clean_dir(name: str) -> str:
    parts = [p for p in (name or "").strip().strip("/").split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def _clamp_timeout(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return int(DEFAULTS["timeout"])
    return max(2, min(20, n))


def load() -> dict:
    """读取配置；文件不存在或损坏时返回默认值。"""
    path = config_path()
    data = dict(DEFAULTS)
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    try:
        url = _clean_url(str(raw.get("url") or ""))
    except ValueError:
        # 手工改坏配置文件时不阻断读取，按未配置处理
        url = ""
    data.update(
        {
            "enabled": bool(raw.get("enabled", False)),
            "url": url,
            "username": str(raw.get("username") or ""),
            "password": str(raw.get("password") or ""),
            "dir": _clean_dir(str(raw.get("dir") or "")),
            "timeout": _clamp_timeout(raw.get("timeout")),
            "verify_tls": bool(raw.get("verify_tls", True)),
        }
    )
    return data


def save(data: dict) -> None:
    """原子写入，避免中途崩溃留下半截 JSON。"""
    with _LOCK:
        path = config_path()
        tmp = path.with_name(path.name + ".tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        try:
            path.chmod(0o600)
        except OSError:
            pass


def public_dict(data: dict | None = None) -> dict:
    """对外展示：隐藏密码，仅告知是否已保存。"""
    d = dict(data or load())
    password = d.pop("password", "")
    d["has_password"] = bool(password)
    return d


def update(payload: dict) -> dict:
    """按显式提供的字段更新配置。

    - password 为空/未提供时保留原密码
    - clear_password=true 时清空密码
    """
    data = load()
    if "enabled" in payload:
        data["enabled"] = bool(payload["enabled"])
    if "url" in payload:
        data["url"] = _clean_url(str(payload["url"] or ""))
    if "username" in payload:
        data["username"] = str(payload["username"] or "").strip()
    if "dir" in payload:
        data["dir"] = _clean_dir(str(payload["dir"] or ""))
    if "timeout" in payload:
        data["timeout"] = _clamp_timeout(payload["timeout"])
    if "verify_tls" in payload:
        data["verify_tls"] = bool(payload["verify_tls"])
    if payload.get("clear_password"):
        data["password"] = ""
    else:
        pwd = payload.get("password")
        if isinstance(pwd, str) and pwd:
            data["password"] = pwd

    if data["enabled"] and not data["url"]:
        raise ValueError("启用同步前请填写 WebDAV 地址")
    save(data)
    return data


def is_configured(data: dict | None = None) -> bool:
    d = data or load()
    return bool(d.get("enabled") and d.get("url"))
