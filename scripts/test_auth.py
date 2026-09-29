#!/usr/bin/env python3
"""账号密码鉴权冒烟：登录 / 会话 / 改密 / 错误密码。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:7311")
USERNAME = os.environ.get("ADMIN_USER", "admin")
PASSWORD = os.environ.get("ADMIN_PASS", "admin123")


def api(path: str, method: str = "GET", data: dict | None = None, token: str | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal ok
        if not cond:
            ok = False
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    st, status = api("/api/auth/status", token="")
    check("status endpoint", st == 200 and "setup_required" in status, str(status))

    st, res = api("/api/auth/login", "POST", {"username": USERNAME, "password": "wrong"}, token="")
    check("bad password rejected", st == 401, str(res))

    st, res = api("/api/auth/login", "POST", {"username": USERNAME, "password": PASSWORD}, token="")
    check("login ok", st == 200 and res.get("token"), str(res)[:80])
    token = res.get("token") or ""

    st, me = api("/api/auth/me", token=token)
    check("me", st == 200 and me.get("username") == USERNAME, str(me))

    st, denied = api("/api/admin/stats", token="")
    check("admin needs session", st == 401)

    st, okstats = api("/api/admin/stats", token=token)
    check("admin with session", st == 200 and "total_books" in (okstats or {}), str(okstats)[:60])

    st, res = api("/api/auth/forgot", "POST", {
        "recovery_code": "0000-0000-0000-0000",
        "new_password": "pass-9999",
    }, token="")
    check("bad recovery rejected", st == 401, str(res))

    print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
