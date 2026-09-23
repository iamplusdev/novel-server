from pathlib import Path
import re

# index.html
p = Path("index.html")
t = p.read_text(encoding="utf-8")
t = re.sub(r'\s*<button id="refresh-btn"[^>]*>刷新</button>', "", t)
t = t.replace(
    '<input id="grid-size" type="range" min="110" max="240" step="10" value="150" />',
    '<input id="grid-size" type="range" min="110" max="240" step="10" value="150" />\n              <input id="list-size" type="range" min="160" max="360" step="10" value="220" hidden />',
)
p.write_text(t, encoding="utf-8")

# admin.css
p = Path("admin.css")
c = p.read_text(encoding="utf-8")
if "/* list cards */" not in c:
    c += """
/* list cards multi-column */
.book-list {
  --list-w: 220px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--list-w), 1fr));
  gap: 10px;
}
.book-row {
  grid-template-columns: 56px 1fr;
  align-items: center;
}
@media (max-width: 860px) {
  .book-list {
    grid-template-columns: repeat(auto-fill, minmax(min(var(--list-w), 100%), 1fr));
  }
}
"""
p.write_text(c, encoding="utf-8")

# admin.js
p = Path("admin.js")
j = p.read_text(encoding="utf-8")
j = j.replace(
    'gridSize: $("grid-size"),',
    'gridSize: $("grid-size"),\n    listSize: $("list-size"),',
)
j = j.replace(
    "applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);",
    "applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);\n  applyListSize(localStorage.getItem('novel_list_size') || 220);",
)
# applyGridSize + applyListSize
if "function applyListSize" not in j:
    j = j.replace(
        "  function applyDrawerWidth(px) {",
        '''  function applyListSize(px) {
    const n = Math.min(360, Math.max(160, Number(px) || 220));
    if (els.listSize) els.listSize.value = String(n);
    if (els.listWrap) els.listWrap.style.setProperty("--list-w", n + "px");
    localStorage.setItem("novel_list_size", String(n));
  }

  function applyDrawerWidth(px) {''',
        1,
    )
# 切换视图时显示对应滑杆
j = j.replace(
    "function renderLibrary() {\n    const grid = state.viewMode === \"grid\";",
    "function renderLibrary() {\n    const grid = state.viewMode === \"grid\";\n    if (els.gridSize) els.gridSize.hidden = !grid;\n    if (els.listSize) els.listSize.hidden = grid;",
    1,
)
# 事件
if "els.listSize.addEventListener" not in j:
    j = j.replace(
        'els.gridSize.addEventListener("input", () => applyGridSize(els.gridSize.value));',
        'els.gridSize.addEventListener("input", () => applyGridSize(els.gridSize.value));\n  els.listSize && els.listSize.addEventListener("input", () => applyListSize(els.listSize.value));',
        1,
    )
p.write_text(j, encoding="utf-8")
print("list multi-col + sliders ok")
