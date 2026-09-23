from pathlib import Path
import re

css = Path("admin.css")
c = css.read_text(encoding="utf-8")

start = c.find("/* —— Book grid")
if start < 0:
    start = c.find(".book-grid {")
end = c.find("/* —— Table")
if end < 0:
    end = c.find(".pager {")
if start < 0:
    start = 0
if end < 0:
    end = len(c)

lib_css = """
/* —— Library cards —— */
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
.book-row .row-side { display: none; }

/* tools */
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
.tools > #search-input { flex: 2 1 180px; }

@media (max-width: 860px) {
  .tools {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .tools > * { min-width: 0 !important; }
  .tools > #search-input { grid-column: 1 / -1; }
  .tools > .size-ctrl { grid-column: 1 / -1; }
  .tools > .btn { width: 100%; justify-content: center; }
  .book-list { grid-template-columns: 1fr; }
}
"""

c = c[:start] + lib_css + "\n" + c[end:]
css.write_text(c, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")
pat = re.compile(
    r'els\.listWrap\.innerHTML = state\.items\.map\(\(b\) => \{[\s\S]*?\}\)\.join\(""\);',
    re.M,
)
new_js = '''els.listWrap.innerHTML = state.items.map((b) => {
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
      }).join("");'''
j2, n = pat.subn(new_js, j, count=1)
js.write_text(j2, encoding="utf-8")
print("library css rebuilt, list js replaced", n)
