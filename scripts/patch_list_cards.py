from pathlib import Path

html = Path("index.html")
t = html.read_text(encoding="utf-8")
t = t.replace('<button id="refresh-btn" class="btn btn-ghost">刷新</button>', "")
t = t.replace(
    '<input id="grid-size" type="range" min="110" max="240" step="10" value="150" />',
    '<input id="grid-size" type="range" min="110" max="240" step="10" value="150" /><input id="list-size" type="range" min="160" max="320" step="10" value="220" hidden />',
)
html.write_text(t, encoding="utf-8")

css = Path("admin.css")
c = css.read_text(encoding="utf-8")
if "/* list multi */" not in c:
    c += """
/* list multi */
.book-list {
  --list-w: 220px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--list-w), 1fr));
  gap: 10px;
}
.book-row { grid-template-columns: 56px 1fr; min-height: 84px; }
"""
css.write_text(c, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")
if "listSize" not in j:
    j = j.replace('gridSize: $("grid-size"),', 'gridSize: $("grid-size"),\n    listSize: $("list-size"),')
if "function applyListSize" not in j:
    j = j.replace(
        "  function applyDrawerWidth(px) {",
        "  function applyListSize(px) {\n    const n = Math.min(320, Math.max(160, Number(px) || 220));\n    if (els.listSize) els.listSize.value = String(n);\n    if (els.listWrap) els.listWrap.style.setProperty('--list-w', n + 'px');\n    localStorage.setItem('novel_list_size', String(n));\n  }\n\n  function applyDrawerWidth(px) {",
        1,
    )
if "applyListSize(localStorage" not in j:
    j = j.replace(
        "applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);",
        "applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);\n  applyListSize(localStorage.getItem('novel_list_size') || 220);",
    )
if 'els.listSize && els.listSize.addEventListener' not in j:
    j = j.replace(
        'els.gridSize.addEventListener("input", () => applyGridSize(els.gridSize.value));',
        'els.gridSize.addEventListener("input", () => applyGridSize(els.gridSize.value));\n  els.listSize && els.listSize.addEventListener("input", () => applyListSize(els.listSize.value));',
        1,
    )
j = j.replace(
    "function renderLibrary() {\n    const grid = state.viewMode === \"grid\";",
    "function renderLibrary() {\n    const grid = state.viewMode === \"grid\";\n    if (els.gridSize) els.gridSize.hidden = !grid;\n    if (els.listSize) els.listSize.hidden = grid;",
    1,
)
js.write_text(j, encoding="utf-8")
print("ok")
