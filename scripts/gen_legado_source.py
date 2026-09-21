"""生成 Legado 书源：根据 novels 分类动态构建 exploreUrl。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import CATEGORIES  # noqa: E402


def build() -> dict:
    return {
        "bookSourceName": "本地小说库",
        "bookSourceGroup": "本地NAS",
        "bookSourceUrl": "http://127.0.0.1:8000",
        "bookSourceType": 0,
        "bookUrlPattern": "",
        "customOrder": 0,
        "enabled": True,
        "enabledCookieJar": False,
        "enabledExplore": True,
        "enabledLogin": False,
        "exploreUrl": [
            {
                "title": c,
                "url": f"/api/legado/explore/{c}?page={{{{page}}}}&page_size=20",
            }
            for c in CATEGORIES
        ],
        "header": "",
        "lastUpdateTime": 0,
        "loginUrl": "",
        "respondTime": 180000,
        "ruleArticles": "",
        "ruleBookInfo": {
            "author": "$.author",
            "coverUrl": "$.cover_url",
            "intro": "$.intro",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "name": "$.name",
            "tocUrl": "$.toc_url",
            "wordCount": "$.word_count",
        },
        "ruleContent": {
            "content": "$.content",
            "nextContentUrl": "",
        },
        "ruleExplore": {
            "bookList": "$.books",
            "author": "$.author",
            "coverUrl": "$.cover_url",
            "intro": "$.intro",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "name": "$.name",
            "tocUrl": "$.toc_url",
        },
        "ruleSearch": {
            "bookList": "$.books",
            "author": "$.author",
            "coverUrl": "$.cover_url",
            "intro": "$.intro",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "name": "$.name",
            "tocUrl": "$.toc_url",
        },
        "ruleToc": {
            "chapterList": "$.chapters",
            "chapterName": "$.name",
            "chapterUrl": "$.content_url",
            "nextTocUrl": "",
        },
        "searchUrl": "/api/legado/search?q={{key}}&page={{page}}&page_size=20",
        "weight": 0,
    }


def main() -> None:
    data = build()
    out = ROOT / "legado_book_source.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
