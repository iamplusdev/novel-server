from pathlib import Path
p = Path("admin.js")
t = p.read_text(encoding="utf-8")
if t.count("{") > t.count("}"):
    t = t.replace("\n})();\n", "\n  }\n})();\n", 1)
    print("inserted }")
p.write_text(t, encoding="utf-8")
print("p", t.count("("), t.count(")"), "b", t.count("{"), t.count("}"))
print(repr(t[-40:]))
