#!/usr/bin/env python3
"""全功能联调：登录/书库/编辑/刮削/体检/备份/导入。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
USER = "admin"
PASS = "admin123"
ok = True


def check(name, cond, detail=""):
    global ok
    if not cond:
        ok = False
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(detail)[:120]) if detail else ""))


def call(path, method="GET", data=None, token="", raw=False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            if raw:
                return r.status, b
            return r.status, (json.loads(b.decode()) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b.decode())
        except Exception:
            return e.code, {"raw": b[:200]}


def main():
    # health
    st, h = call("/health")
    check("health", st == 200 and h.get("ok"), h)

    # auth
    st, s = call("/api/auth/status", token="")
    check("auth status", st == 200 and "setup_required" in s, s)

    st, bad = call("/api/auth/login", "POST", {"username": USER, "password": "wrong"}, token="")
    check("bad login 401", st == 401, bad)

    st, login = call("/api/auth/login", "POST", {"username": USER, "password": PASS}, token="")
    check("login", st == 200 and login.get("token"), login)
    tok = login.get("token") or ""

    st, me = call("/api/auth/me", token=tok)
    check("me", st == 200 and me.get("username") == USER, me)

    st, _ = call("/api/admin/stats", token="")
    check("admin no session 401", st == 401)

    st, stats = call("/api/admin/stats", token=tok)
    check("admin stats", st == 200 and "total_books" in (stats or {}), stats)

    # public
    st, cats = call("/api/categories")
    check("categories", st == 200 and "categories" in (cats or {}), cats)
    st, books = call("/api/books")
    check("public books", st == 200 and books.get("total", 0) >= 1, books.get("total") if books else None)
    bid = books["items"][0]["id"]
    st, detail = call(f"/api/books/{bid}")
    check("book detail", st == 200 and detail.get("id") == bid)
    st, toc = call(f"/api/books/{bid}/chapters")
    check("toc", st == 200 and toc.get("total", 0) >= 1)
    ch = toc["items"][0]
    st, content = call(f"/api/books/{bid}/chapters/{ch['id']}")
    check("content", st == 200 and len((content or {}).get("content") or "") > 5)
    st, search = call("/api/search?q=" + urllib.parse.quote("剑"))
    check("search", st == 200 and "items" in (search or {}))

    # admin books
    st, alist = call("/api/admin/books?sort=words", token=tok)
    check("admin list sort", st == 200 and "items" in (alist or {}))
    st, dups = call("/api/admin/duplicates", token=tok)
    check("duplicates", st == 200 and "items" in (dups or {}))

    st, patched = call(f"/api/admin/books/{bid}", "PATCH", {
        "title": (detail or {}).get("name") or "临时",
        "author": (detail or {}).get("author") or "佚名",
        "tags": "测试,联调",
    }, token=tok)
    check("patch book", st == 200 and "测试" in ((patched or {}).get("tags") or []), (patched or {}).get("tags"))

    # library report/repair
    st, rep = call("/api/admin/library/report", token=tok)
    check("library report", st == 200 and "issues" in (rep or {}))
    st, rep2 = call("/api/admin/library/repair", "POST", {"mode": "clean"}, token=tok)
    check("library repair", st == 200 and "results" in (rep2 or {}))

    # scrape search (qidian)
    st, sc = call("/api/admin/scrape/search", "POST", {
        "keyword": "大奉打更人", "source": "qidian", "limit": 5,
    }, token=tok)
    check("scrape search", st == 200 and "items" in (sc or {}), (sc or {}).get("count"))
    st, det = call("/api/admin/scrape/detail", "POST", {
        "source": "fanqie", "source_book_id": "7276384138653862966",
    }, token=tok)
    check("fanqie detail", st == 200 and (det or {}).get("name"), (det or {}).get("name"))

    # batch status
    st, bs = call("/api/admin/scrape/batch/status", token=tok)
    check("batch status", st == 200 and "running" in (bs or {}))

    # backup config roundtrip
    st, cfg = call("/api/admin/backup/config", token=tok)
    check("backup config get", st == 200 and "webdav_url" in (cfg or {}))
    st, cfg2 = call("/api/admin/backup/config", "PUT", {
        "webdav_url": cfg.get("webdav_url") or "",
        "username": cfg.get("username") or "",
        "remote_path": cfg.get("remote_path") or "novel-server-backups",
        "books_path": cfg.get("books_path") or "books",
        "auto_enabled": False,
        "interval_hours": 24,
        "keep_count": 5,
    }, token=tok)
    check("backup config put", st == 200 and "books_path" in (cfg2 or {}))
    st, bstat = call("/api/admin/backup/status", token=tok)
    check("backup status", st == 200 and "running" in (bstat or {}))

    # import status
    st, ist = call("/api/admin/import/status", token=tok)
    check("import status", st == 200 and "running" in (ist or {}))

    # legado
    st, lb = call("/api/legado/book-source")
    # 书源必须是数组且含 bookUrl 规则，否则 Legado 无法换源
    src0 = (lb[0] if isinstance(lb, list) and lb else (lb if isinstance(lb, dict) else {}))
    check(
        "legado source",
        st == 200
        and isinstance(lb, list)
        and bool(src0.get("bookSourceUrl"))
        and src0.get("ruleSearch", {}).get("bookUrl")
        and src0.get("ruleBookInfo", {}).get("bookUrl"),
    )
    st, lt = call(f"/api/legado/toc/{bid}")
    check("legado toc", st == 200 and lt.get("chapters") is not None)

    # static
    for pth in ("/", "/admin.css", "/admin.js"):
        st, raw = call(pth, raw=True)
        check("static " + pth, st == 200 and raw and len(raw) > 100)

    print("RESULT", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
