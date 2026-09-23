from pathlib import Path
import re

css = Path("admin.css")
c = css.read_text(encoding="utf-8")

# remove appended patch tails that conflict
for marker in (
    "/* list multi */",
    "/* list multi cards */",
    "/* list cards multi-column */",
    "/* settings & tools */",
    "/* settings modern */",
    "/* settings / tool modern */",
    "/* settings / tools */",
    "/* card height patched */",
    "/* equal card height */",
    "/* list multi cards */",
):
    i = c.find(marker)
    if i >= 0:
        c = c[:i]

lib = """
/* —— Library cards (clean) —— */
.book-grid {
  --cover-w: 150px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cover-w), 1fr));
  gap: 14px;
  align-items: stretch;
}
.book-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: border-color .15s, box-shadow .15s;
}
.book-card:hover {
  border-color: var(--accent-border);
  box-shadow: var(--shadow);
}
.book-cover {
  aspect-ratio: 3/4;
  background: var(--cover-bg);
  overflow: hidden;
}
.book-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.book-cover .placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  padding: 8px;
  text-align: center;
  color: var(--placeholder);
  font-size: 12px;
  font-weight: 600;
  word-break: break-all;
}
.book-meta {
  padding: 10px 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.book-name {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.35;
  min-height: 2.7em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.book-sub {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* list: multi-column compact cards */
.book-list {
  --list-w: 240px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--list-w), 1fr));
  gap: 10px;
}
.book-row {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 10px;
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.book-row:hover {
  border-color: var(--accent-border);
  box-shadow: var(--shadow);
}
.book-row .row-cover {
  width: 56px;
  height: 74px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--cover-bg);
  border: 1px solid var(--border);
}
.book-row .row-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.book-row .row-cover .placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  font-size: 10px;
  color: var(--placeholder);
  padding: 2px;
  text-align: center;
  word-break: break-all;
}
.book-row .row-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.book-row .row-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.book-row .row-meta {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.book-row .row-intro,
.book-row .row-side {
  display: none;
}

/* tools row */
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.tools > .btn { flex: 0 0 auto; }
.tools > .input,
.tools > .select,
.tools > .size-ctrl { flex: 1 1 140px; min-width: 0; }
.tools > #search-input { flex: 2 1 200px; }

.panel.card { border-radius: 12px; }

@media (max-width: 860px) {
  .tools {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .tools > * { min-width: 0 !important; }
  .tools > #search-input { grid-column: 1 / -1; }
  .tools > .size-ctrl { grid-column: 1 / -1; }
  .tools > .btn { width: 100%; justify-content: center; }
  .book-list {
    grid-template-columns: 1fr;
  }
}
"""

# replace from first .book-grid block to Table/Panel section
start = c.find("/* —— Book grid")
if start < 0:
    start = c.find(".book-grid {")
end = c.find("/* —— Table")
if end < 0:
    end = c.find("/* —— Panels")
if start >= 0 and end > start:
    c = c[:start] + lib + "\n" + c[end:]
else:
    c = c + "\n" + lib

# ensure mobile media kept for app shell
if "@media (max-width: 860px)" not in c:
    c += """
@media (max-width: 860px) {
  .app { grid-template-columns: 1fr; }
  .sidebar { position: sticky; top: 0; z-index: 20; height: auto; border-right: none; border-bottom: 1px solid var(--border); }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .side-foot { margin-top: 0; flex-direction: row; flex-wrap: wrap; gap: 8px; }
  .main { padding: 12px 12px 32px; }
  .toolbar { flex-direction: column; align-items: stretch; gap: 10px; }
  .drawer { width: 100vw !important; max-width: 100vw; }
  .drawer-resize { display: none; }
}
"""

css.write_text(c, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")
# 列表卡片只显示封面/书名/作者
old_row = j[j.find("els.listWrap.innerHTML") : j.find("els.listWrap.querySelectorAll", j.find("els.listWrap.innerHTML"))]
new_row = '''els.listWrap.innerHTML = state.items.map((b) => {
        const cover = b.cover_url
          ? `<img src="${escapeAttr(b.cover_url)}" alt="" loading="lazy" />`
          : `<div class="placeholder">${escapeHtml((b.name || "").slice(0, 6))}</div>`;
        return `
          <article class="book-row" data-id="${b.id}">
            <div class="row-cover">${cover}</div>
            <div class="row-body">
              <div class="row-title">${escapeHtml(b.name)}</div>
              <div class="row-meta">${escapeHtml(b.author || "佚名")}</div>
            </div>
          </article>`;
      }).join("");
      '''
if "els.listWrap.innerHTML" in j:
    j = j.replace(old_row, new_row, 1)
js.write_text(j, encoding="utf-8")
print("library css/js rebuilt")
