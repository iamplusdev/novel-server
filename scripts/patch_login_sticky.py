from pathlib import Path

p = Path("admin.js")
t = p.read_text(encoding="utf-8")

old = """    const res = await fetch(path, opts);
    const isAuthPath = String(path).indexOf("/api/auth/") === 0;
    if (res.status === 401 && !options?.skipAuth && !isAuthPath) {
      logout(false);
      throw new Error("登录已失效，请重新登录");
    }"""
new = """    const res = await fetch(path, opts);
    const isAuthPath = String(path).indexOf("/api/auth/") === 0;
    // 仅 /me 失效才登出，避免书库等接口 401 把用户踢回登录页
    if (res.status === 401 && !options?.skipAuth && String(path) === "/api/auth/me") {
      logout(false);
      throw new Error("登录已失效，请重新登录");
    }"""
if old in t:
    t = t.replace(old, new, 1)
    print("401 relaxed")
else:
    print("401 pattern miss")

old2 = """    try {
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
    showAuthPane("login");"""
new2 = """    try {
      const me = await api("/api/auth/me", { skipAuth: false });
      if (me && me.username) {
        state.username = me.username;
        showApp();
        try { await afterLogin(); } catch (e) { toast(e.message || "加载数据失败", "err"); }
        return;
      }
    } catch (_) {
      /* cookie/token 都无效则停在登录页 */
    }
    showLogin();
    showAuthPane("login");"""
if old2 in t:
    t = t.replace(old2, new2, 1)
    print("boot showApp first")
else:
    print("boot pattern miss")

p.write_text(t, encoding="utf-8")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
