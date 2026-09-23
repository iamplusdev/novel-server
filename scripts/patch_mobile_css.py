from pathlib import Path

css = Path("admin.css")
t = css.read_text(encoding="utf-8")
start = t.find("/* —— Responsive —— */")
if start < 0:
    start = t.find("@media (max-width: 860px)")
end = t.find("@media (max-width: 480px)")
# cut from Responsive comment or 860 media to end of file media blocks
if start < 0:
    start = len(t)
# remove existing mobile media tails
if "/* —— Responsive —— */" in t:
    t = t[: t.find("/* —— Responsive —— */")]
elif "@media (max-width: 860px)" in t:
    t = t[: t.find("@media (max-width: 860px)")]

t = t.rstrip() + """

/* —— Responsive —— */
@media (max-width: 860px) {
  .app { grid-template-columns: 1fr; }
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 20;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--border);
    padding: 12px;
    gap: 10px;
  }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .nav-item { min-height: 40px; display: flex; align-items: center; }
  .side-foot {
    margin-top: 0;
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .main { padding: 12px 12px 32px; }
  .toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .toolbar-right {
    width: 100%;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  #search-input { width: 100%; flex: 1 1 100%; font-size: 16px; }
  .input, select.input, textarea.input { font-size: 16px; }
  .btn, .btn-sm { min-height: 40px; }
  .book-grid {
    grid-template-columns: repeat(auto-fill, minmax(min(var(--cover-w), 42vw), 1fr));
    gap: 10px;
  }
  .book-row { grid-template-columns: 64px 1fr; }
  .row-side { display: none; }
  .cat-bar {
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 4px;
  }
  .cat-chip { flex: 0 0 auto; }
  .drawer {
    width: 100vw !important;
    max-width: 100vw;
  }
  .drawer-resize { display: none; }
  .cover-edit img { width: 88px; height: 116px; }
  .modal {
    width: min(560px, calc(100vw - 16px));
    max-height: calc(100dvh - 24px);
  }
  .modal .drawer-body { max-height: 55dvh; }
  .form-grid { grid-template-columns: 1fr; }
  .check-item { flex-direction: column; align-items: stretch; }
  .check-item .ops { justify-content: flex-start; }
  .toast {
    left: 12px; right: 12px; bottom: 12px;
    transform: none;
    max-width: none;
    text-align: center;
  }
}

@media (max-width: 480px) {
  .toolbar-right > * { min-width: 0; flex: 1 1 45%; }
  .size-ctrl input[type="range"] { width: 70px; }
  .book-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""
css.write_text(t, encoding="utf-8")
print("mobile css ok")
