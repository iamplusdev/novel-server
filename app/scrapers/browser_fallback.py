"""浏览器兜底：Playwright 连接 fnOS tieron Chrome（CDP），HTTP 刮削失败后使用。

流程：
1. ensure_browser_ready()：唤醒/探测 CDP，等待 runtime ready
2. fetch_html()：connect_over_cdp → 开页 → 取渲染后 HTML → 关页

默认关闭；环境变量 SCRAPER_BROWSER_FALLBACK=1 开启。
CDP_URL 默认 http://127.0.0.1:16002（host 网络下即宿主机网关）。
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request

_lock = threading.Lock()
_ready = False
_last_error = ""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def browser_fallback_enabled() -> bool:
    return _env("SCRAPER_BROWSER_FALLBACK").lower() in ("1", "true", "yes", "on")


def cdp_url() -> str:
    return _env("CDP_URL", "http://127.0.0.1:16002").rstrip("/")


def probe_cdp(timeout: float = 3.0) -> bool:
    """探测 CDP 网关是否可达（GET /json/version）。"""
    url = cdp_url() + "/json/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_browser_ready(wait_seconds: float | None = None) -> bool:
    """唤醒并等待 Chrome runtime ready；超时返回 False。

    fnOS 上 tieron chrome 可能冷启动：先探活，失败则按间隔重试直至超时。
    """
    global _ready, _last_error
    if wait_seconds is None:
        try:
            wait_seconds = float(_env("CDP_READY_WAIT", "20") or "20")
        except ValueError:
            wait_seconds = 20.0
    with _lock:
        if _ready and probe_cdp(timeout=2.0):
            return True
        deadline = time.time() + max(1.0, wait_seconds)
        last = ""
        while time.time() < deadline:
            if probe_cdp(timeout=2.5):
                _ready = True
                _last_error = ""
                return True
            last = "CDP 不可达: " + cdp_url()
            time.sleep(1.5)
        _ready = False
        _last_error = last or ("CDP 不可达: " + cdp_url())
        return False


def last_browser_error() -> str:
    return _last_error


def fetch_text(url: str, *, timeout_ms: int = 30000, wait_ms: int = 800) -> str:
    """在浏览器上下文 fetch URL 并返回文本（兼容 JSON API 与 HTML 页）。"""
    global _ready, _last_error
    if not browser_fallback_enabled():
        raise RuntimeError("浏览器兜底未启用（SCRAPER_BROWSER_FALLBACK）")
    if not ensure_browser_ready():
        raise RuntimeError(_last_error or "浏览器未就绪")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("未安装 playwright，请 pip install -r requirements-optional.txt") from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url())
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                try:
                    page.goto("about:blank", timeout=timeout_ms)
                    text = page.evaluate(
                        """
                        async (u) => {
                          const r = await fetch(u, { credentials: 'include' });
                          return await r.text();
                        }
                        """,
                        url,
                    )
                    if wait_ms:
                        page.wait_for_timeout(min(wait_ms, 300))
                    return text or ""
                finally:
                    page.close()
            finally:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # noqa: BLE001
        _ready = False
        _last_error = f"浏览器抓取失败: {e}"
        raise RuntimeError(_last_error) from e


def fetch_html(url: str, *, timeout_ms: int = 30000, wait_ms: int = 1500) -> str:
    """用宿主 Chrome 渲染页面并返回 HTML；失败抛 RuntimeError。"""
    global _ready, _last_error
    if not browser_fallback_enabled():
        raise RuntimeError("浏览器兜底未启用（SCRAPER_BROWSER_FALLBACK）")
    if not ensure_browser_ready():
        raise RuntimeError(_last_error or "浏览器未就绪")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("未安装 playwright，请 pip install -r requirements-optional.txt") from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url())
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    # 等 SSR/接口填充
                    page.wait_for_timeout(wait_ms)
                    return page.content()
                finally:
                    page.close()
            finally:
                # 不关闭宿主 Chrome，只断开客户端
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # noqa: BLE001
        _ready = False
        _last_error = f"浏览器抓取失败: {e}"
        raise RuntimeError(_last_error) from e
