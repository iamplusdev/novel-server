from pathlib import Path
import re

html = Path("index.html")
t = html.read_text(encoding="utf-8")
t = re.sub(r'<div class="stats" id="stats-box">[\s\S]*?</div>\s*</div>', '', t, count=1)
html.write_text(t, encoding="utf-8")
print("stats removed")
