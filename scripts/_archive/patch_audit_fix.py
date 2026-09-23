from pathlib import Path

for name in ("scripts/smoke_test.py", "scripts/test_webdav_backup.py", "scripts/test_auth.py"):
    p = Path(name)
    if not p.is_file():
        continue
    t = p.read_text(encoding="utf-8")
    t = t.replace('os.environ.get("ADMIN_PASS", "test-pass-12345")', 'os.environ.get("ADMIN_PASS", "admin123")')
    t = t.replace("PASSWORD = os.environ.get(\"ADMIN_PASS\", \"test-pass-12345\")", "PASSWORD = os.environ.get(\"ADMIN_PASS\", \"admin123\")")
    p.write_text(t, encoding="utf-8")

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
t = t.replace('    statBooks: $("stat-books"),\n', "")
t = t.replace('    statWords: $("stat-words"),\n', "")
t = t.replace('    refreshBtn: $("refresh-btn"),\n', "")
t = t.replace('    batchSource: $("batch-source"),\n', "")
while "applyListSize(localStorage.getItem('novel_list_size') || 220);\n  applyListSize(localStorage.getItem('novel_list_size') || 220);" in t:
    t = t.replace("applyListSize(localStorage.getItem('novel_list_size') || 220);\n  applyListSize(localStorage.getItem('novel_list_size') || 220);", "applyListSize(localStorage.getItem('novel_list_size') || 220);")
t = t.replace("els.refreshBtn && els.refreshBtn.addEventListener", "void 0 && els.refreshBtn && els.refreshBtn.addEventListener")
t = t.replace('source: (els.batchSource && els.batchSource.value) || "all",', 'source: "qidian",')
p.write_text(t, encoding="utf-8")
print("patched")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
