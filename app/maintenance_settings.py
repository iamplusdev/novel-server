"""自动体检配置：data/maintenance_settings.json。

只保存调度所需字段；last_scan_at 由调度器触发时写回。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .config import settings

FILE_NAME = "maintenance_settings.json"
DEFAULTS: dict = {
    "scan_enabled": False,
    "scan_interval_hours": 24,
    "scan_deep": False,
    "last_scan_at": "",
    "last_scan_error": "",
}
_LOCK = threading.Lock()


def config_path() -> Path:
    parent = settings.database_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent / FILE_NAME


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _clamp_hours(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return int(DEFAULTS["scan_interval_hours"])
    return max(1, min(720, n))


def load() -> dict:
    """读取配置；文件缺失/损坏时回退默认值。"""
    data = dict(DEFAULTS)
    path = config_path()
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    data.update(
        {
            "scan_enabled": _as_bool(raw.get("scan_enabled"), False),
            "scan_interval_hours": _clamp_hours(raw.get("scan_interval_hours")),
            "scan_deep": _as_bool(raw.get("scan_deep"), False),
            "last_scan_at": str(raw.get("last_scan_at") or ""),
            "last_scan_error": str(raw.get("last_scan_error") or ""),
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


def update(payload: dict) -> dict:
    """更新可编辑字段并保存；last_scan_* 只由调度器维护。"""
    data = load()
    if "scan_enabled" in payload:
        data["scan_enabled"] = _as_bool(payload["scan_enabled"], False)
    if "scan_interval_hours" in payload:
        data["scan_interval_hours"] = _clamp_hours(payload["scan_interval_hours"])
    if "scan_deep" in payload:
        data["scan_deep"] = _as_bool(payload["scan_deep"], False)
    save(data)
    return data


def mark_started(at: str, error: str = "") -> dict:
    data = load()
    data["last_scan_at"] = at or ""
    data["last_scan_error"] = error or ""
    save(data)
    return data


def mark_error(error: str) -> dict:
    data = load()
    data["last_scan_error"] = error or ""
    save(data)
    return data
