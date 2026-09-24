"""生成 Legado 书源：根据 novels 分类动态构建 exploreUrl。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from urllib.parse import quote

from app.config import UNCATEGORIZED, all_category_labels, parse_category_label  # noqa: E402


def build() -> list:
    # Legado 导入要求根节点为书源对象数组，故返回 list
    # 发现页只保留书源两级分类（起点-xxx / 番茄-xxx）+ 未分类，去掉旧扁平分类
    cats = [
        c
        for c in all_category_labels()
        if c == UNCATEGORIZED or parse_category_label(c)[0]
    ]
    return [
        {
            "bookSourceName": "爱小说",
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
                    "url": f"/api/legado/explore/{quote(c, safe='-')}?page={{{{page}}}}&page_size=20",
                }
                for c in cats
            ],
            "header": "",
            "lastUpdateTime": 0,
            "loginUrl": "",
            "respondTime": 180000,
            "ruleArticles": "",
            "ruleBookInfo": {
                "author": "$.author",
                # bookUrl 用于换源/详情定位，缺省会导致目录为空
                "bookUrl": "$.book_url",
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
                "bookUrl": "$.book_url",
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
                "bookUrl": "$.book_url",
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
    ]


def main() -> None:
    data = build()
    out = ROOT / "legado_book_source.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
