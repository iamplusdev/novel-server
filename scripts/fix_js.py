from pathlib import Path

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
needle = "})();"
first = t.find(needle)
second = t.find(needle, first + 1) if first >= 0 else -1
if second >= 0:
    t = t[:first] + t[first + len(needle):]
    print("removed extra iife close")
if t.count("{") > t.count("}"):
    t = t.rstrip() + "\n" + ("}" * (t.count("{") - t.count("}"))) + "\n"
    print("balanced braces")
p.write_text(t, encoding="utf-8")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"), "iife", t.count("})();"))
