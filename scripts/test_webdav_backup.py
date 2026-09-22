#!/usr/bin/env python3
"""WebDAV 备份/还原冒烟测试：依赖 scripts/dev_webdav.py 与本地 novel-server。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.environ.get("ADMIN_USER", "admin")
PASSWORD = os.environ.get("ADMIN_PASS", "test-pass-12345")
TOKEN = os.environ.get("ADMIN_SESSION", "")
DAV_URL = os.environ.get("DAV_URL", "http://127.0.0.1:18080/")


def api(path: str, method: str = "GET", data: dict | None = None, token: str | None = None):
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token if token is not None else TOKEN}"}
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def ensure_session() -> str:
    global TOKEN
    st, st_data = api("/api/auth/status", token="")
    if st_data and st_data.get("setup_required"):
        st, res = api("/api/auth/setup", "POST", {"username": USERNAME, "password": PASSWORD}, token="")
        if st != 200:
            raise RuntimeError(f"setup failed: {res}")
        TOKEN = res["token"]
        return TOKEN
    if TOKEN:
        return TOKEN
    st, res = api("/api/auth/login", "POST", {"username": USERNAME, "password": PASSWORD}, token="")
    if st != 200:
        raise RuntimeError(f"login failed: {res}")
    TOKEN = res["token"]
    return TOKEN


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal ok
        if not cond:
            ok = False
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    ensure_session()

    # 1. 测试连接
    st, res = api("/api/admin/backup/test", "POST", {
        "webdav_url": DAV_URL,
        "username": "test",
        "password": "test",
        "remote_path": "novel-server-backups",
    })
    check("dav test", st == 200 and res.get("ok"), str(res))

    # 2. 保存配置（开启自动也可）
    st, res = api("/api/admin/backup/config", "PUT", {
        "webdav_url": DAV_URL,
        "username": "test",
        "password": "test",
        "remote_path": "novel-server-backups",
        "auto_enabled": False,
        "interval_hours": 24,
        "keep_count": 5,
    })
    saved_url = ((res or {}).get("webdav_url") or "").rstrip("/")
    check("save config", st == 200 and saved_url == DAV_URL.rstrip("/"), str(res)[:120])
    check("password not returned", "password" not in (res or {}), str(list((res or {}).keys())))

    # 3. 执行备份
    st, res = api("/api/admin/backup/run", "POST")
    check("run backup", st == 200 and res.get("remote"), str(res)[:200])
    remote_name = (res or {}).get("remote") or ""
    check("backup has manifest", bool((res or {}).get("manifest")), str((res or {}).get("manifest")))

    # 4. 列表
    st, res = api("/api/admin/backup/list")
    names = [x["name"] for x in (res or {}).get("items") or []]
    check("list remote", st == 200 and remote_name in names, ",".join(names))

    # 5. 改坏一点本地数据后还原（动态查找「九霄剑主」）
    st, cat_books = api("/api/books?category=%E7%8E%84%E5%B9%BB")
    items = (cat_books or {}).get("items") or []
    bid = items[0]["id"] if items else None
    check("find book", bid is not None, str(bid))
    if bid:
        st, res = api(f"/api/admin/books/{bid}", "PATCH", {
            "title": "还原前临时改名",
            "author": "测试",
            "category": "玄幻",
            "status": "完结",
            "tags": "x",
            "intro": "will be restored",
        })
        check("mutate book", st == 200 and res.get("name") == "还原前临时改名")

    st, res = api("/api/admin/backup/restore", "POST", {"filename": remote_name})
    check("restore", st == 200 and res.get("ok"), str(res)[:200])

    if bid:
        st, res = api(f"/api/admin/books/{bid}")
        name = (res or {}).get("name")
        check("restored book name", name == "九霄剑主", f"name={name}")

    st, res = api("/api/admin/stats")
    check("stats after restore", st == 200 and res.get("total_books", 0) >= 3, str(res.get("total_books")))

    # 6. public API 仍可用
    st, res = api("/api/books")
    check("public books ok", st == 200 and res.get("total", 0) >= 3)

    print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
