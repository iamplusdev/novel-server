#!/usr/bin/env python3
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.scrapers.qidian import _http_get

page = _http_get("https://m.qidian.com/book/1019664125/")
i = page.find("tags-wrapper")
print("tags-wrapper ctx:\n", page[i : i + 800] if i >= 0 else "none")
print("---")
# first tagList occurrence context
m = re.search(r'"tagList"\s*:\s*\[', page)
if m:
    print("tagList ctx:\n", page[m.start() - 120 : m.start() + 300])
print("---")
# li.tag links near start of book info
ms = list(re.finditer(r'<li class="tag"[^>]*>\s*<a href="([^"]+)"[^>]*>([^<]+)</a>', page))
print("li.tag count", len(ms))
for x in ms[:12]:
    print(" ", x.group(2), "|", x.group(1)[:60])
