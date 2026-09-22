#!/usr/bin/env python3
"""极简本地 WebDAV 服务（测试用，仅标准库）。

用法:
  python scripts/dev_webdav.py [port] [root_dir]
  默认 18080, ./data/dev_webdav
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.sax.saxutils import escape

USER = os.environ.get("DEV_DAV_USER", "test")
PASS = os.environ.get("DEV_DAV_PASS", "test")


class DavHandler(BaseHTTPRequestHandler):
    root: Path = Path(".")

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("[webdav] " + (fmt % args) + "\n")

    def _authed(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(auth[6:]).decode("utf-8")
        except Exception:
            return False
        return raw == f"{USER}:{PASS}"

    def _send_auth(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="dev-webdav"')
        self.end_headers()

    def _rel_path(self) -> Path:
        path = unquote(urlparse(self.path).path)
        # 去掉开头 /
        rel = path.lstrip("/")
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("path escape")
        return p

    def _ok(self, code: int = 200, body: bytes = b"", ctype: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def do_AUTH(self) -> None:  # pragma: no cover
        pass

    def _guard(self, fn) -> None:
        if not self._authed():
            self._send_auth()
            return
        try:
            fn()
        except ValueError:
            self._ok(403, b"forbidden")
        except FileNotFoundError:
            self._ok(404, b"not found")
        except IsADirectoryError:
            self._ok(405, b"is dir")
        except Exception as e:  # noqa: BLE001
            self._ok(500, str(e).encode())

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("DAV", "1, 2")
        self.send_header("Allow", "OPTIONS, GET, PUT, DELETE, MKCOL, PROPFIND, PROPPATCH")
        self.end_headers()

    def do_GET(self) -> None:
        def fn() -> None:
            p = self._rel_path()
            if p.is_dir():
                self._ok(403, b"is dir")
                return
            data = p.read_bytes()
            self._ok(200, data, "application/octet-stream")

        self._guard(fn)

    def do_PUT(self) -> None:
        def fn() -> None:
            p = self._rel_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else b""
            p.write_bytes(data)
            self._ok(201, b"created")

        self._guard(fn)

    def do_DELETE(self) -> None:
        def fn() -> None:
            p = self._rel_path()
            if p.is_file():
                p.unlink()
                self._ok(204, b"")
            elif p.is_dir():
                import shutil

                shutil.rmtree(p)
                self._ok(204, b"")
            else:
                self._ok(404, b"")

        self._guard(fn)

    def do_MKCOL(self) -> None:
        def fn() -> None:
            p = self._rel_path()
            p.mkdir(parents=True, exist_ok=True)
            self._ok(201, b"")

        self._guard(fn)

    def do_PROPFIND(self) -> None:
        def fn() -> None:
            p = self._rel_path()
            depth = self.headers.get("Depth", "1")
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            if not p.exists() and str(p) != str(self.root.resolve()):
                self._ok(404, b"")
                return

            base = urlparse(self.path).path
            if not base.endswith("/"):
                base += "/"
            entries = []
            if p.is_dir():
                entries.append(p)
                if depth != "0":
                    entries.extend(sorted(p.iterdir()))
            else:
                entries.append(p)

            def item_xml(path: Path) -> str:
                name = path.name if path != self.root.resolve() else ""
                href = base if path.is_dir() and path == p else (base + name if name else base)
                if path.is_dir() and path != p:
                    href = base + name + "/"
                if path == self.root.resolve():
                    href = urlparse(self.path).path
                    if not href.endswith("/"):
                        href += "/"
                lastmod = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                if path.is_dir():
                    return (
                        f'<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>'
                        "<d:resourcetype><d:collection/></d:resourcetype>"
                        f"<d:getlastmodified>{lastmod}</d:getlastmodified>"
                        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                    )
                size = path.stat().st_size
                return (
                    f'<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>'
                    "<d:resourcetype/>"
                    f"<d:getcontentlength>{size}</d:getcontentlength>"
                    f"<d:getlastmodified>{lastmod}</d:getlastmodified>"
                    "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                )

            body = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<d:multistatus xmlns:d="DAV:">' + "".join(item_xml(e) for e in entries) + "</d:multistatus>"
            ).encode("utf-8")
            self.send_response(207)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        self._guard(fn)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/dev_webdav")
    root.mkdir(parents=True, exist_ok=True)
    DavHandler.root = root.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", port), DavHandler)
    print(f"dev WebDAV http://127.0.0.1:{port}/  user={USER} root={root}")
    server.serve_forever()


if __name__ == "__main__":
    main()
