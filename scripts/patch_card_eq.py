from pathlib import Path
import re

p = Path("admin.css")
t = p.read_text(encoding="utf-8")
t = t.replace("align-items: start;", "align-items: stretch;")
if "grid-auto-rows" not in t:
    t = t.replace(".book-grid {", ".book-grid {\n  grid-auto-rows: 1fr;", 1)
t = re.sub(r"\.book-meta\s*\{[^}]*\}", ".book-meta { padding: 10px; display: flex; flex-direction: column; gap: 4px; height: 76px; overflow: hidden; flex: 0 0 76px; }", t, count=1)
t = re.sub(r"\.book-name\s*\{[^}]*\}", ".book-name { font-weight: 600; font-size: 13px; line-height: 1.35; height: 2.7em; flex: 0 0 2.7em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-all; }", t, count=1)
t = re.sub(r"\.book-sub\s*\{[^}]*\}", ".book-sub { color: var(--muted); font-size: 11px; display: flex; flex-wrap: nowrap; gap: 4px; overflow: hidden; white-space: nowrap; }", t, count=1)
p.write_text(t, encoding="utf-8")
print("ok")
