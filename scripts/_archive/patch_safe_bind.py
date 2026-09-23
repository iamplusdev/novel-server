from pathlib import Path
import re

p = Path("admin.js")
t = p.read_text(encoding="utf-8")

# 1) 安全绑定 + 事件区整体 try/catch，保证 bootAuth 一定执行
if "function on(" not in t:
    t = t.replace(
        "  // Events",
        "  function on(el, ev, fn) {\n    if (el && el.addEventListener) el.addEventListener(ev, fn);\n  }\n\n  // Events",
        1,
    )

# 把 els.xxx.addEventListener(...) 换成 on(els.xxx, ...)
t = re.sub(
    r"els\.(\w+)\.addEventListener\(",
    r"on(els.\1, ",
    t,
)

# 2) boot 前兜底：确保 bootAuth 一定执行
t = t.replace(
    "  bootAuth().catch((e) => {\n    showLogin();\n    showAuthPane(\"login\");\n    authError(e.message || \"无法连接服务端\");\n  });",
    "  Promise.resolve()\n    .then(() => bootAuth())\n    .catch((e) => {\n      showLogin();\n      showAuthPane(\"login\");\n      authError(e.message || \"无法连接服务端\");\n    });",
    1,
)

p.write_text(t, encoding="utf-8")
print("on binds", t.count("on(els."))
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
