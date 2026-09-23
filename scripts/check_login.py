import json
import urllib.request
from pathlib import Path

body = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/auth/login",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=8)
    print("api", r.status)
except Exception as e:
    print("api_err", e)

js = Path("admin.js").read_text(encoding="utf-8")
h = Path("index.html").read_text(encoding="utf-8")
print("loginBtn bind", "els.loginBtn.addEventListener" in js)
print("function login", "async function login(" in js)
print("loginUser ref", "els.loginUser" in js)
print("iife", js.count("})();"), "paren", js.count("("), js.count(")"), "brace", js.count("{"), js.count("}"))
for i in ["login-user", "login-pass", "login-btn", "auth-login", 'id="login"', 'id="app"']:
    print(i, i in h)
