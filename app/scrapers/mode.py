"""刮削取数方式：API 直连 / fnOS Chrome（CDP 浏览器）/ 自动。

- api    ：纯 HTTP（默认）
- chrome ：强制走浏览器 CDP（fnOS tieron Chrome）
- auto   ：自动检测 fnOS Chrome，可用则优先 Chrome，失败回退 API；不可用则纯 API
"""
from __future__ import annotations

import threading

MODE_API = "api"
MODE_CHROME = "chrome"
MODE_AUTO = "auto"
VALID_MODES = (MODE_API, MODE_CHROME, MODE_AUTO)

_lock = threading.Lock()
# 默认 API 直连：Chrome 仅作备用（显式选择或 API 失败且开关允许时兜底）
_current_mode = MODE_API


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
    """前端下拉用的可选项说明（api/chrome 为单一通道，auto 才有两段）。"""
    return [
        {"value": MODE_API, "label": "API 直连", "hint": "默认：只走 HTTP，不与浏览器互兜底"},
        {
            "value": MODE_AUTO,
            "label": "自动（API 优先）",
            "hint": "API 优先；失败后再用 Chrome 兜底（唯一的两段式）",
        },
        {
            "value": MODE_CHROME,
            "label": "Chrome 浏览器",
            "hint": "强制走浏览器，不与 API 互兜底；需 CDP/Playwright 环境支持",
        },
    ]
