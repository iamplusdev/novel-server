from pathlib import Path
import re

h = Path("index.html")
t = h.read_text(encoding="utf-8")
# 内联登录成功后保存 token，刷新才能进入后台
t = t.replace(
    'post("/api/auth/login", { username: u, password: p }).then(function (res) {\n          if (!res.ok) return showErr((res.data && res.data.detail) || "登录失败");\n          location.reload();\n        })',
    'post("/api/auth/login", { username: u, password: p }).then(function (res) {\n          if (!res.ok) return showErr((res.data && res.data.detail) || "登录失败");\n          if (res.data && res.data.token) {\n            try { localStorage.setItem("novel_admin_token", res.data.token); } catch (e) {}\n          }\n          location.reload();\n        })',
)
# setup 同样保存 token
t = t.replace(
    'if (res.data && res.data.recovery_code) {\n            alert("请保存恢复码：\\n" + res.data.recovery_code);\n          }\n          location.reload();',
    'if (res.data && res.data.token) {\n            try { localStorage.setItem("novel_admin_token", res.data.token); } catch (e) {}\n          }\n          if (res.data && res.data.recovery_code) {\n            alert("请保存恢复码：\\n" + res.data.recovery_code);\n          }\n          location.reload();',
)
h.write_text(t, encoding="utf-8")

j = Path("admin.js")
s = j.read_text(encoding="utf-8")
# bootAuth：无 localStorage token 时也尝试 Cookie 会话
s = s.replace(
    """    if (state.token) {
      try {
        const me = await api("/api/auth/me");
        state.username = me.username;
        await afterLogin();
        return;
      } catch (_) {
        state.token = "";
        localStorage.removeItem(TOKEN_KEY);
      }
    }
    showLogin();
    showAuthPane("login");""",
    """    try {
      const me = await api("/api/auth/me");
      if (me && me.username) {
        state.username = me.username;
        await afterLogin();
        return;
      }
    } catch (_) {
      state.token = "";
      localStorage.removeItem(TOKEN_KEY);
    }
    showLogin();
    showAuthPane("login");""",
    1,
)
j.write_text(s, encoding="utf-8")
print("token persist + cookie boot ok")
