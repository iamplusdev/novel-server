#!/usr/bin/env python3
"""端到端 API 冒烟测试（UTF-8 安全）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:7311")
USERNAME = os.environ.get("ADMIN_USER", "admin")
PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
TOKEN = os.environ.get("ADMIN_SESSION", "")


def fetch(path: str, method: str = "GET", data: dict | None = None, token: str | None = None):
    url = BASE + path
    headers = {"Accept": "application/json"}
    body = None
    if token is None:
        token = TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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
    st, st_data = fetch("/api/auth/status", token="")
    if st_data and st_data.get("setup_required"):
        st, res = fetch("/api/auth/setup", "POST", {"username": USERNAME, "password": PASSWORD}, token="")
        if st != 200:
            raise RuntimeError(f"setup failed: {res}")
        TOKEN = res["token"]
        return TOKEN
    if TOKEN:
        return TOKEN
    st, res = fetch("/api/auth/login", "POST", {"username": USERNAME, "password": PASSWORD}, token="")
    if st != 200:
        raise RuntimeError(f"login failed: {res}")
    TOKEN = res["token"]
    return TOKEN


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    checks = []

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        checks.append(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

    ensure_session()
    st, health = fetch("/health")
    check("health", st == 200 and health.get("ok") is True, str(health))

    st, cats = fetch("/api/categories")
    check("categories", st == 200 and cats.get("total_books", 0) >= 3, f"total={cats.get('total_books')}")

    st, books = fetch("/api/books")
    items = books.get("items") if st == 200 else []
    check("books list", st == 200 and len(items) >= 3, f"n={len(items) if items else 0}")
    if items:
        names = [b["name"] for b in items]
        check("utf-8 book names", any("剑" in n or "霄" in n or "空" in n for n in names), ",".join(names))

    st, search = fetch("/api/search?q=" + urllib.parse.quote("剑"))
    check("search 剑", st == 200 and search.get("total", 0) >= 1, f"total={search.get('total')}")

    # find 玄幻 book
    st, cat_books = fetch("/api/books?category=" + urllib.parse.quote("玄幻"))
    check("category filter", st == 200 and cat_books.get("total", 0) >= 1)
    bid = cat_books["items"][0]["id"] if st == 200 and cat_books.get("items") else None

    if bid:
        st, detail = fetch(f"/api/books/{bid}")
        check("book detail", st == 200 and detail.get("id") == bid, detail.get("name", ""))
        check("absolute urls", str(detail.get("toc_url", "")).startswith("http"), detail.get("toc_url", ""))

        st, toc = fetch(f"/api/books/{bid}/chapters")
        check("toc", st == 200 and toc.get("total", 0) >= 3, f"chapters={toc.get('total')}")
        ch = toc["items"][0]
        st, content = fetch(f"/api/books/{bid}/chapters/{ch['id']}")
        check("content", st == 200 and len(content.get("content", "")) > 20)
        check(
            "chapter parse",
            "第一章" in content.get("title", "") or "灵根" in content.get("title", ""),
            content.get("title", ""),
        )

        st, lexp = fetch("/api/legado/explore/" + urllib.parse.quote("玄幻"))
        check("legado explore", st == 200 and lexp.get("books"), f"n={len(lexp.get('books') or [])}")
        if lexp.get("books"):
            b0 = lexp["books"][0]
            check(
                "legado full urls",
                b0.get("toc_url", "").startswith("http") and b0.get("detail_url", "").startswith("http"),
                b0.get("toc_url", ""),
            )
        st, ltoc = fetch(f"/api/legado/toc/{bid}")
        check("legado toc", st == 200 and ltoc.get("chapters"), f"n={len(ltoc.get('chapters') or [])}")
        if ltoc.get("chapters"):
            cu = ltoc["chapters"][0]["content_url"]
            check("legado content url abs", cu.startswith("http"), cu)
            path = urllib.parse.urlparse(cu).path
            st, lc = fetch(path)
            check("legado content", st == 200 and "content" in lc and len(lc["content"]) > 20)

        st, src = fetch("/api/legado/book-source")
        # 书源须为数组（Legado 导入格式），并带 bookUrl 规则
        src0 = (src[0] if isinstance(src, list) and src else (src if isinstance(src, dict) else {}))
        check("book-source", st == 200 and src0.get("bookSourceUrl", "").startswith("http"), src0.get("bookSourceUrl", ""))
        check("book-source array", isinstance(src, list) and len(src) >= 1)
        check("book-source bookUrl rule", bool(src0.get("ruleSearch", {}).get("bookUrl")))
        check("book-source explore", bool(src0.get("exploreUrl")))

        st, unauth = fetch("/api/admin/stats", token="")
        check("admin 401 without session", st == 401)

        st, me = fetch("/api/auth/me")
        check("auth me", st == 200 and bool(me.get("username")), str(me))

        st, stats = fetch("/api/admin/stats", token=TOKEN)
        check("admin stats", st == 200 and stats.get("total_books", 0) >= 3)

        st, patched = fetch(
            f"/api/admin/books/{bid}",
            method="PATCH",
            data={
                "title": "九霄剑主",
                "author": "苏寒",
                "category": "玄幻",
                "status": "连载",
                "tags": "剑修, 热血, 系统流",
                "intro": "九霄大陆，宗门林立。杂役少年苏寒偶得残破玉简……",
            },
            token=TOKEN,
        )
        check("admin patch", st == 200 and patched.get("status") == "连载", json.dumps(patched, ensure_ascii=False)[:120])
        check("admin tags", patched.get("tags") == ["剑修", "热血", "系统流"], str(patched.get("tags")))

        st, alist = fetch("/api/admin/books?q=" + urllib.parse.quote("苏寒"), token=TOKEN)
        check("admin search", st == 200 and alist.get("total", 0) >= 1)

    req = urllib.request.Request(BASE + "/")
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8")
    check("index.html", "爱小说" in html or "id=\"app\"" in html)
    for asset in ("/legado_book_source.json", "/api/auth/status"):
        req = urllib.request.Request(BASE + asset)
        with urllib.request.urlopen(req, timeout=10) as resp:
            check(f"asset {asset}", resp.status == 200)

    print("\n".join(checks))
    print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
