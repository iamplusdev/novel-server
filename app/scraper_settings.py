"""刮削参数运行时配置。

默认值来自环境变量；可由 `data/scraper_settings.json` 覆盖，并在管理后台「设置」页调节。
- get(key)：取当前生效值
- get_all()：全部生效值
- spec()：每个参数的类型/范围/说明（前端渲染用）
- update(patch)：校验、合并、原子写盘、即时生效
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .config import settings

_LOCK = threading.Lock()
_FILE_NAME = "scraper_settings.json"
_cache: dict | None = None


def _env_float(key: str, default: float) -> float:
    raw = (os.environ.get(key) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = (os.environ.get(key) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _defaults() -> dict:
    """环境变量默认值（未在设置页保存过时生效）。"""
    return {
        "delay": max(0.3, _env_float("SCRAPER_DELAY", 2.0)),
        "jitter_max": max(0.0, _env_float("SCRAPER_JITTER_MAX", 1.5)),
        "long_pause_every": max(0, _env_int("SCRAPER_LONG_PAUSE_EVERY", 5)),
        "long_pause_min": max(0.0, _env_float("SCRAPER_LONG_PAUSE_MIN", 5.0)),
        "long_pause_max": max(0.0, _env_float("SCRAPER_LONG_PAUSE_MAX", 15.0)),
        "host_min_interval": max(0.0, _env_float("SCRAPER_HOST_MIN_INTERVAL", 2.0)),
        "host_jitter_max": max(0.0, _env_float("SCRAPER_HOST_JITTER_MAX", 0.6)),
        "retry_max": max(0, _env_int("SCRAPER_RETRY_MAX", 3)),
        "retry_base": max(0.0, _env_float("SCRAPER_RETRY_BASE", 2.0)),
        "respect_retry_after": _env_int("SCRAPER_RESPECT_RETRY_AFTER", 1) != 0,
    }


# 每个参数：类型 + 允许范围 + 展示信息
SPEC: dict[str, dict] = {
    "delay": {"type": "float", "min": 0.3, "max": 120, "label": "书间基础间隔", "unit": "秒"},
    "jitter_max": {"type": "float", "min": 0, "max": 120, "label": "书间抖动上限", "unit": "秒"},
    "long_pause_every": {"type": "int", "min": 0, "max": 10000, "label": "每 N 本长休息", "unit": "本", "hint": "0=关闭"},
    "long_pause_min": {"type": "float", "min": 0, "max": 600, "label": "长休息最短", "unit": "秒"},
    "long_pause_max": {"type": "float", "min": 0, "max": 600, "label": "长休息最长", "unit": "秒"},
    "host_min_interval": {"type": "float", "min": 0, "max": 120, "label": "同域最小间隔", "unit": "秒", "hint": "0=关闭"},
    "host_jitter_max": {"type": "float", "min": 0, "max": 120, "label": "同域间隔抖动", "unit": "秒"},
    "retry_max": {"type": "int", "min": 0, "max": 20, "label": "退避重试次数", "unit": "次", "hint": "命中 429/403/503 时"},
    "retry_base": {"type": "float", "min": 0, "max": 120, "label": "退避基数", "unit": "秒", "hint": "指数增长"},
    "respect_retry_after": {"type": "bool", "label": "尊重 Retry-After", "hint": "按站点响应头等待"},
}


def _coerce(key: str, value):
    spec = SPEC[key]
    t = spec["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    n = int(float(value)) if t == "int" else float(value)
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def _path() -> Path:
    return settings.database_path.parent / _FILE_NAME


def _load_file() -> dict:
    p = _path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if k in SPEC:
            try:
                out[k] = _coerce(k, v)
            except (TypeError, ValueError):
                continue
    return out


def _effective() -> dict:
    global _cache
    with _LOCK:
        if _cache is None:
            _cache = {**_defaults(), **_load_file()}
        return dict(_cache)


def get(key: str):
    """取单个参数当前生效值（未保存过则回退环境变量默认）。"""
    return _effective().get(key, _defaults().get(key))


def get_all() -> dict:
    return _effective()


def spec() -> list[dict]:
    return [{"key": k, **v} for k, v in SPEC.items()]


def update(patch: dict) -> dict:
    """按 range 校验并保存到 data/scraper_settings.json，返回最新生效值。"""
    global _cache
    with _LOCK:
        cur = {**_defaults(), **(_cache or _load_file())}
        for k, v in (patch or {}).items():
            if k not in SPEC:
                continue
            try:
                cur[k] = _coerce(k, v)
            except (TypeError, ValueError):
                continue
        # 长休息区间兜底：最大不得小于最小
        if cur.get("long_pause_max", 0) < cur.get("long_pause_min", 0):
            cur["long_pause_min"], cur["long_pause_max"] = (
                cur["long_pause_max"],
                cur["long_pause_min"],
            )
        _cache = cur
        path = _path()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return dict(cur)


def reset_cache() -> None:
    global _cache
    with _LOCK:
        _cache = None
