import re
import urllib.request

h = urllib.request.urlopen("http://127.0.0.1:8000/").read().decode()
print("refs", re.findall(r'(?:src|href)="([^"]+)"', h))
for p in ["/admin.css", "/admin.js", "/favicon.ico", "/legado_book_source.json"]:
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000" + p)
        print(p, r.status)
    except Exception as e:
        print(p, type(e).__name__, e)
