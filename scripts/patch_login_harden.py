from pathlib import Path
import re

html = Path("index.html")
t = html.read_text(encoding="utf-8")
t = re.sub(r"<button(?![^>]*type=)", '<button type="button"', t)
html.write_text(t, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")

j = j.replace(
    """  function showApp() {
    els.login.hidden = true;
    els.app.hidden = false;
    els.viewMode.value = state.viewMode;
    if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
    renderCategoryBar();
  }""",
    """  function showApp() {
    try {
      if (els.login) els.login.hidden = true;
      if (els.app) els.app.hidden = false;
      if (els.viewMode) els.viewMode.value = state.viewMode;
      if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
      if (els.categoryBar) renderCategoryBar();
    } catch (e) {
      if (els.login) els.login.hidden = true;
      if (els.app) els.app.hidden = false;
    }
  }""",
)

j = j.replace(
    """      saveSession(res);
      state.username = res.username;
      els.loginPass.value = "";
      await afterLogin();""",
    """      saveSession(res);
      state.username = res.username;
      if (els.loginPass) els.loginPass.value = "";
      showApp();
      await afterLogin();""",
)

js.write_text(j, encoding="utf-8")
print("login harden ok")
