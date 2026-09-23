from pathlib import Path
import re

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
t = re.sub(
    r'<div class="book-sub">[\s\S]*?</div>\s*</div>\s*</article>',
    '''<div class="book-sub">
                <span>${escapeHtml(b.author || "佚名")}</span>
              </div>
            </div>
          </article>''',
    t,
    count=1,
)
p.write_text(t, encoding="utf-8")
print("ok")
