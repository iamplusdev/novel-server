"""刮削取数方式：API 直连 / fnOS Chrome（CDP 浏览器）/ 自动。

- api    ：纯 HTTP（默认）
- chrome ：强制走浏览器 CDP（fnOS tieron Chrome）
- auto   ：先 API，失败后自动切浏览器重试
"""
from __future__ import annotations

import threading

MODE_API = "api"
MODE_CHROME = "chrome"
MODE_AUTO = "auto"
VALID_MODES = (MODE_API, MODE_CHROME, MODE_AUTO)

_lock = threading.Lock()
# 默认自动：与历史「HTTP 失败再浏览器兜底」行为兼容
_current_mode = MODE_AUTO


def normalize_mode(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    if v in ("browser", "fnos", "fnos-chrome", "cdp"):
        return MODE_CHROME
    if v in VALID_MODES:
        return v
    return MODE_AUTO


def get_scrape_mode() -> str:
    with _lock:
        return _current_mode


def set_scrape_mode(mode: str) -> str:
    """设置进程内默认刮削方式（会话级偏好，重启后回到 auto）。"""
    global _current_mode
    m = normalize_mode(mode)
    with _lock:
        _current_mode = m
    return m


def mode_uses_browser(mode: str | None = None) -> bool:
    m = normalize_mode(mode) if mode is not None else get_scrape_mode()
    return m == MODE_CHROME


def describe_modes() -> list[dict]:
    """前端下拉用的可选项说明。"""
    return [
        {"value": MODE_API, "label": "API 直连", "hint": "轻量 HTTP 请求，速度快"},
        {"value": MODE_CHROME, "label": "Chrome 浏览器", "hint": "经 fnOS Chrome / CDP 渲染取页，抗风控更强"},
        {"value": MODE_AUTO, "label": "自动", "hint": "优先 API，失败后自动切 Chrome"},
    ]
