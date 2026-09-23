from pathlib import Path

p = Path("admin.js")
lines = p.read_text(encoding="utf-8").splitlines()
dp = 0
db = 0
for i, line in enumerate(lines, 1):
    dp += line.count("(") - line.count(")")
    db += line.count("{") - line.count("}")
print("end", dp, db)
if dp > 0:
    t = "\n".join(lines) + ("\n)" * dp) + "\n"
    p.write_text(t, encoding="utf-8")
    print("appended", dp, ")")
