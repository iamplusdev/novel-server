from pathlib import Path
import re

p = Path("admin.js")
t = p.read_text(encoding="utf-8")

t = re.sub(
    r'setText\(els\.authSubtitle, ("[^"]*")\s*;',
    r'setText(els.authSubtitle, \1);',
    t,
)

t = t.replace(
    "els.statBooks.textContent = data.total_books ?? 0;",
    "if (els.statBooks) els.statBooks.textContent = data.total_books ?? 0;",
)
t = t.replace(
    "els.statWords.textContent = fmtWords(data.total_words);",
    "if (els.statWords) els.statWords.textContent = fmtWords(data.total_words);",
)

if "function setText(" not in t:
    t = t.replace(
        "  function toast(msg, type) {",
        "  function setText(el, v) {\n    if (el) el.textContent = v;\n  }\n\n  function toast(msg, type) {",
        1,
    )

p.write_text(t, encoding="utf-8")
print("fixed", "if (els.statBooks)" in t)
print("bad leftover", bool(re.search(r'setText\(els\.authSubtitle, "[^"]+"\s*;\n', t)))
