from pathlib import Path

p = Path("admin.css")
t = p.read_text(encoding="utf-8")
t = t.replace(
    ".book-meta { padding: 10px; display: flex; flex-direction: column; gap: 4px; min-height: 72px; }",
    ".book-meta { padding: 10px; display: flex; flex-direction: column; gap: 4px; height: 72px; overflow: hidden; }",
)
t = t.replace(
    "  -webkit-line-clamp: 2;\n  -webkit-box-orient: vertical;\n  overflow: hidden;\n}",
    "  height: 2.7em;\n  -webkit-line-clamp: 2;\n  -webkit-box-orient: vertical;\n  overflow: hidden;\n  word-break: break-all;\n}",
    1,
)
t = t.replace("align-items: start;", "align-items: stretch;")
p.write_text(t, encoding="utf-8")
print("ok")
