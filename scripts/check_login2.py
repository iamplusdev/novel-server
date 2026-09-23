from pathlib import Path
import re
js = Path("admin.js").read_text(encoding="utf-8")
h = Path("index.html").read_text(encoding="utf-8")
print("loginBtn on()", "on(els.loginBtn, \"click\", login)" in js or "on(els.loginBtn," in js)
print("broken on on", js.count("on(els.") , js.count("addEventListener"))
print("double on", "on(els." in js and "on(on(" in js)
# 显示 login 相关绑定
for line in js.splitlines():
    if "loginBtn" in line or "setupBtn" in line or "function login" in line:
        print("JS:", line.strip()[:120])
print("--- html login ---")
i = h.find('id="login"')
print(h[i:i+500] if i>=0 else "NO LOGIN")
print("auth-login hidden?", 'id="auth-login"' in h)
