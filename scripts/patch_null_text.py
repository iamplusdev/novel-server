from pathlib import Path

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
t = t.replace(
    "els.statBooks.textContent = data.total_books ?? 0;",
    "if (els.statBooks) els.statBooks.textContent = data.total_books ?? 0;",
)
t = t.replace(
    "els.statWords.textContent = fmtWords(data.total_words);",
    "if (els.statWords) els.statWords.textContent = fmtWords(data.total_words);",
)
t = t.replace(
    "els.baseUrlLabel.textContent = data.public_base_url || location.origin;",
    "if (els.baseUrlLabel) els.baseUrlLabel.textContent = data.public_base_url || location.origin;",
)
t = t.replace(
    "els.libCount.textContent = String(state.total);",
    "if (els.libCount) els.libCount.textContent = String(state.total);",
)
t = t.replace(
    "els.pageLabel.textContent = state.page + \" / \" + pages;",
    "if (els.pageLabel) els.pageLabel.textContent = state.page + \" / \" + pages;",
)
p.write_text(t, encoding="utf-8")
print("null-safe ok")
