from pathlib import Path

html = Path("index.html")
t = html.read_text(encoding="utf-8")

if "data-view=\"settings\"" not in t:
    t = t.replace(
        '<button class="nav-item" data-view="api">API / 书源</button>',
        '<button class="nav-item" data-view="api">API / 书源</button>\n        <button class="nav-item" data-view="settings">设置</button>',
    )

start = t.find('<div class="side-foot">')
end = t.find("</aside>", start)
if start >= 0 and end > start:
    t = t[:start] + '<div class="side-foot">\n        <button class="btn btn-ghost btn-sm" data-view="settings">设置</button>\n      </div>\n    ' + t[end:]

if "view-settings" not in t:
    sec = '''
      <section id="view-settings" class="view" hidden>
        <header class="toolbar"><div class="toolbar-left"><h2>设置</h2></div></header>
        <div class="panel card">
          <div class="panel-title">外观</div>
          <label class="field"><span>主题</span>
            <select id="theme-select" class="input select">
              <option value="auto">跟随系统</option>
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </label>
        </div>
        <div class="panel card">
          <div class="panel-title">账号</div>
          <div class="row">
            <button id="change-pass-btn" class="btn btn-primary">修改密码</button>
            <button id="logout-btn" class="btn btn-ghost">退出登录</button>
          </div>
        </div>
      </section>
'''
    t = t.replace("    </main>", sec + "    </main>", 1)

html.write_text(t, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")
j = j.replace(
    '["library", "import", "check", "backup", "api"]',
    '["library", "import", "check", "backup", "api", "settings"]',
)
js.write_text(j, encoding="utf-8")

css = Path("admin.css")
c = css.read_text(encoding="utf-8")
if "settings & tools" not in c:
    c += """
/* settings & tools */
.panel.card { border-radius: 12px; }
.tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
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
}
"""
css.write_text(c, encoding="utf-8")
print("settings ui patched")
