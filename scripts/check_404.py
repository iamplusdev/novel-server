import re
import urllib.request

BASE = "http://127.0.0.1:7311"
h = urllib.request.urlopen(BASE + "/").read().decode()
print("refs", re.findall(r'(?:src|href)="([^"]+)"', h))
for p in ["/favicon.ico", "/legado_book_source.json", "/api/auth/status", "/health"]:
    try:
        r = urllib.request.urlopen(BASE + p)
        print(p, r.status)
    except Exception as e:
        print(p, type(e).__name__, e)
