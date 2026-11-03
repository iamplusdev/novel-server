"""统计接口的进程内短 TTL 缓存。

统计聚合会扫多张表；短缓存避免频繁刷新页面重复计算。
默认 30 秒，STATS_CACHE_TTL=0 可关闭。
"""
from __future__ import annotations

import os
import threading
import time

_TTL = max(0.0, float(os.environ.get("STATS_CACHE_TTL", "30") or "30"))
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, object]] = {}


def _now() -> float:
    return time.monotonic()


def get(key: str):
    if _TTL <= 0:
        return None
    with _LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= _now():
            _CACHE.pop(key, None)
            return None
        return value


def set(key: str, value) -> None:  # noqa: A001 - 模块内简单 API
    if _TTL <= 0:
        return
    with _LOCK:
        _CACHE[key] = (_now() + _TTL, value)


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
