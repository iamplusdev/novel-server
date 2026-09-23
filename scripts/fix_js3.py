from pathlib import Path
p = Path("admin.js")
t = p.read_text(encoding="utf-8")
i = t.rfind("})();")
if i >= 0:
    t = t[: i + 6] + "\n"
p.write_text(t, encoding="utf-8")
print(repr(t[-30:]))
print(t.count("("), t.count(")"), t.count("{"), t.count("}"))
