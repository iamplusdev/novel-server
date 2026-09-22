from pathlib import Path

p = Path("app/batch_scrape.py")
t = p.read_text(encoding="utf-8")
t = t.replace('source: str = "qidian"', 'source: str = "all"')
if "ALL_SOURCES" not in t:
    t = t.replace(
        "from .scrapers import REGISTRY, SOURCE_LABELS",
        "from .scrapers import ALL_SOURCES, REGISTRY, SOURCE_LABELS",
    )
p.write_text(t, encoding="utf-8")

p = Path("app/routers/batch_scrape.py")
t = p.read_text(encoding="utf-8")
t = t.replace('default="qidian"', 'default="all"')
p.write_text(t, encoding="utf-8")

p = Path("index.html")
t = p.read_text(encoding="utf-8")
needle = '<button id="batch-scrape-status" class="btn btn-ghost">刷新进度</button>'
insert = (
    needle
    + '\n            <select id="batch-source" class="input select" title="刮削源">'
    + '<option value="all">全部源</option><option value="qidian">仅起点</option>'
    + '<option value="fanqie">仅番茄</option></select>'
)
if "batch-source" not in t and needle in t:
    t = t.replace(needle, insert, 1)
p.write_text(t, encoding="utf-8")

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
if "batchSource" not in t:
    t = t.replace(
        'batchMinScore: $("batch-min-score"),',
        'batchMinScore: $("batch-min-score"),\n    batchSource: $("batch-source"),',
        1,
    )
t = t.replace(
    'source: "qidian",\n          only_missing:',
    'source: (els.batchSource && els.batchSource.value) || "all",\n          only_missing:',
)
t = t.replace(
    'source: "qidian",\n          source_book_id:',
    'source: (els.scrapeSource && els.scrapeSource.value) || "qidian",\n          source_book_id:',
)
p.write_text(t, encoding="utf-8")
print("patched ok")
