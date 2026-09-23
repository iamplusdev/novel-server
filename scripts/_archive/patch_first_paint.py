from pathlib import Path

# 首屏默认显示「创建账号」，避免数据清空后仍看到登录框
h = Path("index.html")
t = h.read_text(encoding="utf-8")
t = t.replace('<div id="auth-login">', '<div id="auth-login" hidden>', 1)
t = t.replace('<div id="auth-setup" hidden>', '<div id="auth-setup">', 1)
t = t.replace('id="auth-subtitle">管理后台 · 账号登录', 'id="auth-subtitle">首次使用 · 请创建管理账号', 1)
h.write_text(t, encoding="utf-8")

js = Path("admin.js")
j = js.read_text(encoding="utf-8")
old = """  async function login() {
    const username = els.loginUser.value.trim();
    const password = els.loginPass.value;
    if (!username || !password) {
      authError("请输入用户名和密码");
      return;
    }"""
new = """  async function login() {
    try {
    const username = (els.loginUser && els.loginUser.value || "").trim();
    const password = (els.loginPass && els.loginPass.value) || "";
    if (!username || !password) {
      authError("请输入用户名和密码");
      return;
    }"""
if old in j:
    j = j.replace(old, new, 1)
    j = j.replace(
        """    } catch (err) {
      const msg = (err && err.message) || "登录失败";
      if (String(msg).indexOf("尚未设置") >= 0 || String(msg).indexOf("创建") >= 0) {
        showAuthPane("setup");
        authError("首次使用请先创建账号（下方表单）");
      } else {
        authError(msg);
      }
    }
  }""",
        """    } catch (err) {
      const msg = (err && err.message) || "登录失败";
      if (String(msg).indexOf("尚未设置") >= 0 || String(msg).indexOf("创建") >= 0) {
        showAuthPane("setup");
        authError("首次使用请先创建账号（下方表单）");
      } else {
        authError(msg);
      }
    }
    } catch (e) {
      authError(e.message || "登录失败");
    }
  }""",
        1,
    )
    print("login try wrap")
else:
    print("login pattern miss")
js.write_text(j, encoding="utf-8")
print("paren", j.count("("), j.count(")"), "brace", j.count("{"), j.count("}"))
