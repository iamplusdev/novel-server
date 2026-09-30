"""浏览器兜底：Playwright 连接 fnOS tieron Chrome（CDP），HTTP 刮削失败后使用。

流程：
1. ensure_browser_ready()：唤醒/探测 CDP，等待 runtime ready
2. fetch_text()：真实导航取响应正文（HTML/JSON）
3. fetch_html()：导航后取渲染 HTML
4. warmup()：预热站点 Cookie，丢弃正文

CDP 连接在进程内复用（_get_browser），page 每次新建。
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
# chrome_available 探测结果缓存（避免 auto 每本书都探一次 CDP）
_detect_lock = threading.Lock()
_detect_cache: bool | None = None
_detect_at = 0.0
_DETECT_TTL = 60.0

# 进程内共享 Playwright / CDP 连接（避免每次取页都握手）
_pw = None
_browser = None
_conn_lock = threading.Lock()


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def browser_fallback_enabled() -> bool:
    """浏览器模式是否可用。

    任一条件满足即可：
    1. 环境变量 SCRAPER_BROWSER_FALLBACK=1
    2. 当前刮削方式为 chrome
    3. 本次调用已 set_browser_mode(True)（请求指定 chrome / auto 重试）
    """
    if _env("SCRAPER_BROWSER_FALLBACK").lower() in ("1", "true", "yes", "on"):
        return True
    try:
        from .mode import MODE_CHROME, get_scrape_mode

        if get_scrape_mode() == MODE_CHROME:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import http_util

        # 不调用 browser_mode()（它会含 chrome 模式判断），直接看强制开关
        if http_util.is_browser_mode_forced():
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


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


def playwright_installed() -> bool:
    """Playwright 是否已安装（CDP 连接需要它，缺包时不能宣称 Chrome 可用）。"""
    import importlib.util

    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def chrome_available(timeout: float = 1.5, *, ttl: float = _DETECT_TTL) -> bool:
    """检测 fnOS Chrome（CDP + Playwright）是否真正可用；结果短时缓存。

    与 ensure_browser_ready 不同：只做轻量探活，不冷启动等待。
    auto 模式据此决定优先 Chrome 还是纯 API：
    CDP 可达但缺 Playwright 时视为不可用，避免运行时报「未安装 playwright」。
    """
    global _detect_cache, _detect_at
    now = time.time()
    with _detect_lock:
        if _detect_cache is not None and (now - _detect_at) < ttl:
            return _detect_cache
    ok = playwright_installed() and probe_cdp(timeout=timeout)
    with _detect_lock:
        _detect_cache = ok
        _detect_at = time.time()
    return ok


def reset_chrome_detect_cache() -> None:
    """清空探测缓存（换环境 / 手动刷新时用）。"""
    global _detect_cache, _detect_at
    with _detect_lock:
        _detect_cache = None
        _detect_at = 0.0


def _get_browser():
    """获取已连接的 Browser；断开则重连。调用方负责 page 的开关。"""
    global _pw, _browser
    with _conn_lock:
        if _browser is not None:
            try:
                if _browser.is_connected():
                    return _browser
            except Exception:  # noqa: BLE001
                pass
            _browser = None
        # 旧连接失效：先释放再重建
        if _pw is not None:
            try:
                _pw.stop()
            except Exception:  # noqa: BLE001
                pass
            _pw = None
        from playwright.sync_api import sync_playwright

        _pw = sync_playwright().start()
        _browser = _pw.chromium.connect_over_cdp(cdp_url())
        return _browser


def _drop_browser() -> None:
    """连接不可用时丢弃缓存，下次取页自动重连。"""
    global _pw, _browser
    with _conn_lock:
        if _browser is not None:
            try:
                # CDP 模式下 close 仅断开客户端，不关宿主 Chrome
                _browser.close()
            except Exception:  # noqa: BLE001
                pass
        if _pw is not None:
            try:
                _pw.stop()
            except Exception:  # noqa: BLE001
                pass
        _pw = None
        _browser = None


def _page_extra_headers(headers: dict | None = None, referer: str = "") -> dict[str, str]:
    """仅透传影响内容协商的请求头；UA 保留 Chrome 自身，避免改指纹。"""
    allow = {"accept", "referer", "accept-language"}
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if v and str(k).lower() in allow:
            out[str(k)] = str(v)
    if referer and "referer" not in {x.lower() for x in out}:
        out["Referer"] = referer
    return out


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


def _open_page(headers: dict | None = None, referer: str = ""):
    """在共享 browser 上开新页；返回 (browser, page)。调用方负责 page.close()。"""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as e:
        raise RuntimeError("未安装 playwright，请 pip install -r requirements-optional.txt") from e
    browser = _get_browser()
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    extra = _page_extra_headers(headers, referer)
    if extra:
        # Accept/Referer 等内容协商头；UA 不覆盖，保留 Chrome 指纹
        page.set_extra_http_headers(extra)
    return browser, page


def _handle_fetch_error(url: str, e: Exception) -> None:
    """统一错误收尾：记录 URL、连接失效则丢缓存。"""
    global _ready, _last_error
    _ready = False
    _last_error = f"浏览器抓取失败: {url} · {e}"
    try:
        if _browser is None or not _browser.is_connected():
            _drop_browser()
    except Exception:  # noqa: BLE001
        _drop_browser()


def fetch_text(
    url: str,
    *,
    timeout_ms: int = 30000,
    wait_ms: int = 800,
    headers: dict | None = None,
    referer: str = "",
) -> str:
    """用宿主 Chrome 真实导航取响应正文（兼容 JSON API 与 HTML 页）。

    注意：
    1. 不要用 about:blank + 页内 fetch——null 源跨源请求会被 CORS 拦（Failed to fetch）。
    2. 不要等 goto 返回后再 resp.text()——页面二次跳转后 body 会被丢弃；
       应在 response 事件里立刻抓主文档 body（见下方 _on_response）。
    3. CDP 连接进程内复用；page 每次新建，避免串状态。
    """
    if not browser_fallback_enabled():
        raise RuntimeError("浏览器兜底未启用（SCRAPER_BROWSER_FALLBACK）")
    if not ensure_browser_ready():
        raise RuntimeError(_last_error or "浏览器未就绪")

    try:
        _, page = _open_page(headers, referer)
        try:
            # 响应体必须在「页面二次导航」前读取，否则 Playwright 会丢弃 body
            # （No resource with given identifier / navigated away from）。
            # 故用 response 事件在响应到达时立刻抓取，而非 goto 之后再 resp.text()。
            captured: dict[str, str] = {}

            def _on_response(response) -> None:
                if "text" in captured:
                    return
                try:
                    # 只抓主文档导航响应（跳过 css/js/xhr 等子资源）
                    if response.request.is_navigation_request() and response.frame == page.main_frame:
                        captured["text"] = response.text()
                except Exception:  # noqa: BLE001
                    pass

            page.on("response", _on_response)
            try:
                # commit = 收到响应即返回，减少与页面二次跳转的竞态
                resp = page.goto(url, wait_until="commit", timeout=timeout_ms)
                if "text" not in captured:
                    if resp is None:
                        raise RuntimeError(f"导航无响应: {url}")
                    # 兜底：goto 刚返回、尚未二次导航时立刻取 body
                    captured["text"] = resp.text()
                text = captured["text"]
            finally:
                page.remove_listener("response", _on_response)
            if wait_ms:
                page.wait_for_timeout(min(wait_ms, 300))
            return text or ""
        finally:
            page.close()
    except Exception as e:  # noqa: BLE001
        _handle_fetch_error(url, e)
        raise RuntimeError(_last_error) from e


def fetch_html(
    url: str,
    *,
    timeout_ms: int = 30000,
    wait_ms: int = 1500,
    headers: dict | None = None,
    referer: str = "",
) -> str:
    """用宿主 Chrome 渲染页面并返回 HTML；失败抛 RuntimeError。"""
    if not browser_fallback_enabled():
        raise RuntimeError("浏览器兜底未启用（SCRAPER_BROWSER_FALLBACK）")
    if not ensure_browser_ready():
        raise RuntimeError(_last_error or "浏览器未就绪")

    try:
        _, page = _open_page(headers, referer)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # 等 SSR/接口填充
            page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            page.close()
    except Exception as e:  # noqa: BLE001
        _handle_fetch_error(url, e)
        raise RuntimeError(_last_error) from e


def warmup(url: str, *, timeout_ms: int = 15000) -> bool:
    """预热站点会话（拿 Cookie / msToken 等），丢弃正文。失败不抛。"""
    try:
        fetch_text(url, timeout_ms=timeout_ms, wait_ms=0)
        return True
    except Exception:  # noqa: BLE001
        return False
