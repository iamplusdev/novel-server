"""极简 WebDAV 客户端（仅标准库 urllib + ElementTree）。"""
from __future__ import annotations

import base64
import posixpath
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

DAV_NS = "d"
PROPFIND_BODY = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>
"""


@dataclass
class DavItem:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: str = ""


class WebDAVError(Exception):
    pass


class WebDAVClient:
    def __init__(self, base_url: str, username: str = "", password: str = "", timeout: int = 60):
        if not base_url or not base_url.startswith(("http://", "https://")):
            raise WebDAVError("WebDAV 地址必须以 http:// 或 https:// 开头")
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout

    def _auth_header(self) -> dict[str, str]:
        if not self.username and not self.password:
            return {}
        raw = f"{self.username}:{self.password}".encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}

    def _url(self, rel_path: str) -> str:
        rel = (rel_path or "").lstrip("/")
        # 先解码再编码，避免 %E7%… 被二次转义成 %25E7%…
        parts = [quote(unquote(p), safe="") for p in rel.split("/") if p not in ("", ".")]
        suffix = "/".join(parts)
        return urljoin(self.base_url, suffix) if suffix else self.base_url

    def request(
        self,
        method: str,
        rel_path: str = "",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        url = self._url(rel_path)
        hdrs = {"User-Agent": "novel-server-webdav/1.0", **self._auth_header()}
        if headers:
            hdrs.update(headers)
        req = Request(url, data=data, headers=hdrs, method=method)
        try:
            with urlopen(req, timeout=timeout or self.timeout) as resp:
                body = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, body, resp_headers
        except HTTPError as e:
            body = e.read() if e.fp else b""
            if e.code in (200, 201, 204, 207):
                return e.code, body, {k.lower(): v for k, v in (e.headers or {}).items()}
            raise WebDAVError(f"{method} {url} 失败: HTTP {e.code} {body[:200]!r}") from e
        except URLError as e:
            raise WebDAVError(f"{method} {url} 连接失败: {e.reason}") from e

    def options(self) -> bool:
        try:
            status, _, _ = self.request("OPTIONS", "")
            return status < 500
        except WebDAVError:
            return False

    def exists(self, rel_path: str) -> bool:
        probe = rel_path
        if rel_path and not rel_path.endswith("/"):
            probe = rel_path + "/"
        try:
            status, _, _ = self.request("PROPFIND", probe, data=PROPFIND_BODY.encode(), headers={
                "Depth": "0",
                "Content-Type": "application/xml; charset=utf-8",
            })
            return status in (200, 207)
        except WebDAVError:
            return False

    def list_dir_names(self, rel_path: str = "") -> list[str]:
        """只返回子目录名，便于路径探测。"""
        return sorted(i.name for i in self.list_items(rel_path) if i.is_dir)

    def mkdir(self, rel_path: str) -> None:
        """递归创建集合（已存在则忽略）。"""
        rel = (rel_path or "").strip("/")
        if not rel:
            return
        parts = rel.split("/")
        cur = []
        for part in parts:
            cur.append(part)
            path = "/".join(cur)
            if self.exists(path):
                continue
            try:
                status, _, _ = self.request("MKCOL", path)
                if status not in (200, 201, 204, 301):
                    raise WebDAVError(f"MKCOL {path} HTTP {status}")
            except WebDAVError:
                # 并发创建时对方可能先成功
                if not self.exists(path):
                    raise

    def list_items(self, rel_path: str = "") -> list[DavItem]:
        # 集合 PROPFIND 带尾斜杠，兼容只认 path/ 的网盘
        probe = rel_path
        if rel_path and not rel_path.endswith("/"):
            probe = rel_path + "/"
        status, body, _ = self.request(
            "PROPFIND",
            probe,
            data=PROPFIND_BODY.encode(),
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        )
        if status not in (200, 207):
            raise WebDAVError(f"PROPFIND 失败: HTTP {status}")
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            raise WebDAVError(f"WebDAV 响应解析失败: {e}") from e

        base_path = self._url(rel_path)
        self_norm = posixpath.normpath(unquote(urlparse(base_path).path)).replace("\\", "/")
        if not self_norm.startswith("/"):
            self_norm = "/" + self_norm
        items: list[DavItem] = []

        for resp in root.findall(f"{{{ 'DAV:' }}}response"):
            href_el = resp.find(f"{{{ 'DAV:' }}}href")
            if href_el is None or not href_el.text:
                continue
            href = href_el.text
            href_path = unquote(urlparse(href).path)
            norm = posixpath.normpath(href_path).replace("\\", "/")
            if not norm.startswith("/"):
                norm = "/" + norm
            # 跳过集合自身，避免 novels/科幻/科幻 这种重复下钻
            if norm.rstrip("/") == self_norm.rstrip("/"):
                continue

            name = unquote(posixpath.basename(norm.rstrip("/")))
            if not name:
                continue

            prop = resp.find(f".//{{{ 'DAV:' }}}prop")
            is_dir = False
            size = 0
            modified = ""
            if prop is not None:
                rt = prop.find(f"{{{ 'DAV:' }}}resourcetype")
                if rt is not None and rt.find(f"{{{ 'DAV:' }}}collection") is not None:
                    is_dir = True
                cl = prop.find(f"{{{ 'DAV:' }}}getcontentlength")
                if cl is not None and cl.text and cl.text.isdigit():
                    size = int(cl.text)
                lm = prop.find(f"{{{ 'DAV:' }}}getlastmodified")
                if lm is not None and lm.text:
                    modified = lm.text
            items.append(DavItem(name=name, path=norm, is_dir=is_dir, size=size, modified=modified))
        return items

    def list_names(self, rel_path: str = "") -> list[str]:
        return sorted(i.name for i in self.list_items(rel_path) if not i.is_dir)

    def put_file(self, rel_path: str, data: bytes) -> None:
        status, _, _ = self.request(
            "PUT",
            rel_path,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=max(self.timeout, 120),
        )
        if status not in (200, 201, 204):
            raise WebDAVError(f"PUT {rel_path} 失败: HTTP {status}")

    def get_file(self, rel_path: str) -> bytes:
        status, body, _ = self.request("GET", rel_path, timeout=max(self.timeout, 120))
        if status != 200:
            raise WebDAVError(f"GET {rel_path} 失败: HTTP {status}")
        return body

    def delete(self, rel_path: str) -> None:
        status, _, _ = self.request("DELETE", rel_path)
        if status not in (200, 204, 404):
            raise WebDAVError(f"DELETE {rel_path} 失败: HTTP {status}")

    def test_connection(self) -> str:
        self.request("OPTIONS", "")
        # 尝试列出根路径
        try:
            self.list_items("")
            return "连接成功"
        except WebDAVError as e:
            # 某些服务对 PROPFIND 权限不同，OPTIONS 成功也算部分可用
            return f"OPTIONS 成功，列表权限受限: {e}"
