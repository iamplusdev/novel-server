from pathlib import Path
p = Path("admin.js")
t = p.read_text(encoding="utf-8")
old = "    }\n  \n\n  const TOKEN_KEY"
new = "    }\n  })();\n\n  const TOKEN_KEY"
if old in t:
    t = t.replace(old, new, 1)
    print("closed stripAigc")
else:
    print("pattern miss")
p.write_text(t, encoding="utf-8")
print("p", t.count("("), t.count(")"), "b", t.count("{"), t.count("}"))
