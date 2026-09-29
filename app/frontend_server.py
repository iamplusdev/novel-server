"""前端静态服务（默认 :7311）：托管 Vue dist，并把 API 前缀反代到后端。

浏览器只访问前端端口：静态资源本机直出，/api 等转发到后端（默认 :7312），
从而保持同源 HttpOnly Cookie 会话可用。
"""
from __future__ import annotations

import http.client
import mimetypes
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# 需要反代到后端的路径前缀
PROXY_PREFIXES = (
    "/api",
    "/covers",
    "/health",
    "/legado_book_source.json",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# 逐跳头，不转发
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _should_proxy(path: str) -> bool:
    for p in PROXY_PREFIXES:
        if path == p or path.startswith(p + "/") or path.startswith(p + "?"):
            return True
    return False


class FrontendHandler(SimpleHTTPRequestHandler):
    """静态 + SPA 回退 + API 反代。"""

    # 由 serve() 注入
    dist_dir: Path
    api_host: str
    api_port: int

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.dist_dir), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        # 精简日志，避免刷屏
        print(f"[frontend] {self.address_string()} {fmt % args}")

    # ---- 反代 ----
    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        conn = http.client.HTTPConnection(self.api_host, self.api_port, timeout=300)
        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in _HOP_BY_HOP:
                headers[k] = v
        try:
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in _HOP_BY_HOP or k.lower() == "set-cookie":
                    # Set-Cookie 必须原样转发（同源 Cookie 会话）
                    self.send_header(k, v)
            # 用 Content-Length 或分块都可；SSE 靠持续读写
            raw_len = resp.getheader("Content-Length")
            if raw_len is not None:
                self.send_header("Content-Length", raw_len)
            self.end_headers()
            # 流式转发（兼容 SSE）
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except BrokenPipeError:
                    break
        except Exception as e:  # noqa: BLE001 — 反代失败返回 502
            try:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                msg = f"Bad Gateway: {e}".encode("utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            except Exception:
                pass
        finally:
            conn.close()

    # ---- 静态 / SPA ----
    def _send_file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _serve_spa_or_file(self) -> None:
        rel = urlsplit(self.path).path.lstrip("/")
        # 防目录穿越
        candidate = (self.dist_dir / rel).resolve()
        try:
            candidate.relative_to(self.dist_dir.resolve())
        except ValueError:
            candidate = self.dist_dir / "index.html"
        if candidate.is_file():
            self._send_file(candidate)
            return
        # history 路由回退
        index = self.dist_dir / "index.html"
        if not index.is_file():
            self.send_response(503)
            msg = b"frontend not built: cd frontend && npm run build"
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        self._send_file(index)

    def do_GET(self) -> None:
        if _should_proxy(urlsplit(self.path).path):
            self._proxy()
        else:
            self._serve_spa_or_file()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()


def serve_forever(
    *,
    dist_dir: Path,
    host: str,
    port: int,
    api_host: str,
    api_port: int,
) -> ThreadingHTTPServer:
    """启动前端 HTTP 服务（阻塞当前线程）。"""
    handler = type(
        "BoundFrontendHandler",
        (FrontendHandler,),
        {"dist_dir": dist_dir, "api_host": api_host, "api_port": api_port},
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.serve_forever()
    return httpd


def start_in_thread(
    *,
    dist_dir: Path,
    host: str,
    port: int,
    api_host: str,
    api_port: int,
) -> threading.Thread:
    t = threading.Thread(
        target=serve_forever,
        kwargs={
            "dist_dir": dist_dir,
            "host": host,
            "port": port,
            "api_host": api_host,
            "api_port": api_port,
        },
        daemon=True,
        name="frontend-http",
    )
    t.start()
    return t
