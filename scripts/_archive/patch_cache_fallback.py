from pathlib import Path
import time

h = Path("index.html")
t = h.read_text(encoding="utf-8")
ver = str(int(time.time()))
t = t.replace('src="/admin.js"', f'src="/admin.js?v={ver}"')
t = t.replace('href="/admin.css"', f'href="/admin.css?v={ver}"')

# 内联兜底：即使 admin.js 未加载也能完成首设/登录
if "inline-auth-fallback" not in t:
    inject = """
  <script id="inline-auth-fallback">
    (function () {
      function toast(msg) {
        var el = document.getElementById("login-error");
        if (el) { el.hidden = false; el.textContent = msg; }
      }
      function post(path, body) {
        return fetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }).then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
        });
      }
      window.doSetup = function () {
        var u = (document.getElementById("setup-user") || {}).value || "";
        var p = (document.getElementById("setup-pass") || {}).value || "";
        var p2 = (document.getElementById("setup-pass2") || {}).value || "";
        u = u.trim();
        if (!u) return toast("请填写用户名");
        if (!p || p.length < 6) return toast("密码至少 6 位");
        if (p !== p2) return toast("两次密码不一致");
        post("/api/auth/setup", { username: u, password: p }).then(function (res) {
          if (!res.ok) return toast((res.data && res.data.detail) || "创建失败");
          if (res.data && res.data.recovery_code) {
            alert("请保存恢复码：\\n" + res.data.recovery_code);
          }
          location.reload();
        }).catch(function (e) { toast(String(e)); });
      };
      window.doLogin = function () {
        var u = (document.getElementById("login-user") || {}).value || "";
        var p = (document.getElementById("login-pass") || {}).value || "";
        u = u.trim();
        if (!u || !p) return toast("请输入用户名和密码");
        post("/api/auth/login", { username: u, password: p }).then(function (res) {
          if (!res.ok) return toast((res.data && res.data.detail) || "登录失败");
          location.reload();
        }).catch(function (e) { toast(String(e)); });
      };
    })();
  </script>
"""
    t = t.replace('<script src="/admin.js', inject + '  <script src="/admin.js', 1)
    print("fallback injected")
h.write_text(t, encoding="utf-8")
print("ver", ver)
