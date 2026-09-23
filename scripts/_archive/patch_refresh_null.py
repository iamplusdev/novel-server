from pathlib import Path
p = Path("admin.js")
t = p.read_text(encoding="utf-8")
t = t.replace(
    'els.refreshBtn.addEventListener("click", () => loadBooks().catch((e) => toast(e.message, "err")));',
    'els.refreshBtn && els.refreshBtn.addEventListener("click", () => loadBooks().catch((e) => toast(e.message, "err")));',
)
p.write_text(t, encoding="utf-8")
print("ok")
