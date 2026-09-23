from pathlib import Path
h = Path("index.html").read_text(encoding="utf-8")
for s in ['id="login"', 'id="app"', 'login-user', 'login-pass', 'login-btn', 'auth-login', 'id="view-library"', 'id="view-settings"', 'id="view-backup"', 'id="view-check"', 'id="view-import"', 'id="view-api"']:
    print(s, s in h)
print("app snippet", h[h.find('id="app"'):h.find('id="app"')+250])
