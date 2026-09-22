from pathlib import Path

p = Path("app/scrapers/fanqie.py")
t = p.read_text(encoding="utf-8")
old = """    # 简介正文块
    if not hit.intro:
        m = re.search(
            r'class=\"[^\"]*(?:page-abstract|book-abstract|abstract)[^\"]*\"[^>]*>([\\s\\S]*?)</(?:p|div)>',
            page,
        )
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(r'<meta name=\"description\" content=\"([^\"]+)\"', page)
        if m:
            hit.intro = _clean(m.group(1))[:500]"""
new = """    # 简介：目录前正文段 / abstract / meta description
    if not hit.intro:
        m = re.search(
            r'class=\"[^\"]*(?:page-abstract|book-abstract|abstract|book-info)[^\"]*\"[^>]*>([\\s\\S]{10,800}?)</(?:p|div)>',
            page,
        )
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(r'>([^<]{20,400})</p></div><div class=\"page-directory-header\"', page)
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(r'\"abstract\"\\s*:\\s*\"([^\"]{10,500})\"', page)
        if m:
            try:
                raw = bytes(m.group(1), \"utf-8\").decode(\"unicode_escape\")
            except Exception:
                raw = m.group(1)
            hit.intro = _clean(raw)[:500]
    if not hit.intro:
        m = re.search(r'<meta name=\"description\" content=\"([^\"]+)\"', page)
        if m:
            hit.intro = _clean(m.group(1))[:500]"""
if old in t:
    t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")

p = Path("index.html")
t = p.read_text(encoding="utf-8")
t = t.replace(
    '<select id="batch-source" class="input select" title="刮削源"><option value="all">全部源</option><option value="qidian">仅起点</option><option value="fanqie">仅番茄</option></select>',
    "",
)
t = t.replace(
    """<select id="batch-source" class="input select" title="刮削源">
              <option value="all">全部源</option>
              <option value="qidian">仅起点</option>
              <option value="fanqie">仅番茄</option>
            </select>""",
    "",
)
t = t.replace(
    "按现有刮削源（起点/番茄）对书库批量识别",
    "按起点对书库批量识别（番茄仅书号单独刮，不参与一键）",
)
p.write_text(t, encoding="utf-8")

p = Path("app/routers/batch_scrape.py")
t = p.read_text(encoding="utf-8")
t = t.replace('default="all"', 'default="qidian"')
p.write_text(t, encoding="utf-8")

p = Path("app/batch_scrape.py")
t = p.read_text(encoding="utf-8")
t = t.replace('source: str = "all"', 'source: str = "qidian"')
p.write_text(t, encoding="utf-8")
print("patched intro + batch qidian-only")
