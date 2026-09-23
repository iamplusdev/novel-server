from pathlib import Path

p = Path("admin.js")
t = p.read_text(encoding="utf-8")

old = """    const res = await fetch(path, opts);
    if (res.status === 401) {
      logout(false);
      throw new Error("Token 无效或已过期");
    }"""
new = """    const res = await fetch(path, opts);
    const isAuthPath = String(path).indexOf("/api/auth/") === 0;
    if (res.status === 401 && !options?.skipAuth && !isAuthPath) {
      logout(false);
      throw new Error("登录已失效，请重新登录");
    }"""
if old in t:
    t = t.replace(old, new, 1)
    print("fixed 401")
else:
    print("401 pattern miss")

old2 = """    try {
      const res = await api("/api/auth/login", {
        method: "POST",
        body: { username: username, password: password },
      });"""
new2 = """    try {
      state.token = "";
      localStorage.removeItem(TOKEN_KEY);
      const res = await api("/api/auth/login", {
        method: "POST",
        skipAuth: true,
        body: { username: username, password: password },
      });"""
if old2 in t:
    t = t.replace(old2, new2, 1)
    print("fixed login token")
else:
    print("login pattern miss")

p.write_text(t, encoding="utf-8")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
