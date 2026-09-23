from pathlib import Path
t = Path("admin.js").read_text(encoding="utf-8")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
print("iife", t.count("})();"))
print(repr(t[-200:]))
import re
for i, line in enumerate(t.splitlines(), 1):
    if line.strip() in ("})", "})()", "})();"):
        if i > 1500 or i < 30:
            print(i, line)
