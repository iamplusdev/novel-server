from pathlib import Path
p = Path("admin.js")
t = p.read_text(encoding="utf-8")
t = t.replace('document.querySelectorAll(".nav-item").forEach', 'document.querySelectorAll("[data-view]").forEach')
p.write_text(t, encoding="utf-8")
print("nav ok")
