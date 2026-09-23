"""刮削 / 外联 HTTP 统一出口：默认直连，避免被系统代理（本地 Clash 等）拖垮。

策略：
1. 优先直连（ProxyHandler({})），不读 Windows / 环境代理。
2. 若设置了 SCRAPER_PROXY（如 http://127.0.0.1:7890），则优先走该代理。
3. 直连失败时，回退系统代理再试一次（兼容必须翻墙才可达的源）。
"""
from __future__ import annotations

import gzip
import os
import urllib.error
import urllib.request


class HttpError(Exception):
    """网络请求失败（连接/超时/HTTP 等）。"""


def _proxy_handler() -> urllib.request.ProxyHandler:
    proxy = (os.environ.get("SCRAPER_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if proxy:
        return urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    # 显式空代理 = 直连，不继承系统代理
    return urllib.request.ProxyHandler({})


def _system_proxy_handler() -> urllib.request.ProxyHandler:
    # 回退：交给 urllib 读系统 / 环境代理
    return urllib.request.ProxyHandler()


def _open(req: urllib.request.Request, timeout: int):
    """先直连（或指定代理），失败再回退系统代理。"""
    try:
        opener = urllib.request.build_opener(_proxy_handler())
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError:
        # HTTP 状态码错误与网络无关，直接抛出
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as first:
        try:
            opener = urllib.request.build_opener(_system_proxy_handler())
            return opener.open(req, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as second:
            raise HttpError(f"连接失败(直连/代理均不可用): {second}") from first


def http_get(
    url: str,
    headers: dict | None = None,
    timeout: int = 20,
    referer: str = "",
) -> str:
    """GET 并按 gzip / charset 解码为文本。"""
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip",
    }
    if referer:
        hdrs["Referer"] = referer
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with _open(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        raise HttpError(f"请求失败 HTTP {e.code}") from e


def http_get_bytes(
    url: str,
    headers: dict | None = None,
    timeout: int = 20,
    referer: str = "",
) -> tuple[bytes, str]:
    """GET 原始字节（封面下载等），返回 (data, content_type)。"""
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    if referer:
        hdrs["Referer"] = referer
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with _open(req, timeout=timeout) as resp:
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            return data, ctype
    except urllib.error.HTTPError as e:
        raise HttpError(f"下载失败 HTTP {e.code}") from e
