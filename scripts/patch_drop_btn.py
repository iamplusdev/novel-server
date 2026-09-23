from pathlib import Path

html = Path("index.html")
t = html.read_text(encoding="utf-8")
# 删除侧栏等处多余「设置」按钮，保留导航菜单
t = t.replace('<button class="btn btn-ghost btn-sm" data-view="settings">设置</button>', "")
html.write_text(t, encoding="utf-8")
print("ok")
