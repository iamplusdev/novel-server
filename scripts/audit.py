#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
js = (root / "admin.js").read_text(encoding="utf-8")
html = (root / "index.html").read_text(encoding="utf-8")
print("== admin.js ==")
print("paren", js.count("("), js.count(")"))
print("brace", js.count("{"), js.count("}"))
print("iife", js.count("})();"))
print("== els missing ==")
els_keys = re.findall(r"(\w+):\s*\$\(\"([^\"]+)\"\)", js)
print([(k, i) for k, i in els_keys if f'id="{i}"' not in html])
print("== FE API ==")
fe = sorted(set(re.findall(r'api\(\s*[`\"\'](/api/[^`\"\'?]+)', js)))
print("\n".join(fe))
print("== BE routes ==")
be = []
for p in (root / "app").rglob("*.py"):
    t = p.read_text(encoding="utf-8")
    m = re.search(r'APIRouter\(prefix=\"([^\"]*)\"', t)
    pre = m.group(1) if m else ""
    for mm in re.finditer(r'@router\.(get|post|patch|delete|put)\(\"([^\"]+)\"', t):
        be.append(mm.group(1).upper() + " " + pre + mm.group(2))
print("\n".join(sorted(set(be))))
