from pathlib import Path
import re

h = Path("index.html")
t = h.read_text(encoding="utf-8")

# 登录/创建表单默认：登录可见；由脚本按 status 切换
t = t.replace('<div id="auth-login" hidden>', '<div id="auth-login">', 1)
t = t.replace('<div id="auth-setup">', '<div id="auth-setup" hidden>', 1)

# 替换内联脚本为：自动切换表单 + 登录/创建
new_script = r'''
  <script id="inline-auth-fallback">
    (function () {
      function $(id) { return document.getElementById(id); }
      function showErr(msg) {
        var el = $("login-error");
        if (el) { el.hidden = false; el.textContent = msg || ""; }
      }
      function showPane(name) {
        if ($("auth-login")) $("auth-login").hidden = name !== "login";
        if ($("auth-setup")) $("auth-setup").hidden = name !== "setup";
        if ($("auth-forgot")) $("auth-forgot").hidden = true;
        if ($("auth-recovery")) $("auth-recovery").hidden = true;
        if ($("auth-subtitle")) {
          $("auth-subtitle").textContent = name === "setup"
            ? "首次使用 · 请创建管理账号"
            : "管理后台 · 账号登录";
        }
      }
      function post(path, body) {
        return fetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }).then(function (r) {
          return r.text().then(function (txt) {
            var data = null;
            try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = { detail: txt }; }
            return { ok: r.ok, status: r.status, data: data };
          });
        });
      }
      // 按服务端状态切换登录/创建
      fetch("/api/auth/status").then(function (r) { return r.json(); }).then(function (st) {
        showPane(st && st.setup_required ? "setup" : "login");
      }).catch(function () { showPane("login"); });

      window.doSetup = function () {
        var u = (($("setup-user") || {}).value || "").trim();
        var p = ($("setup-pass") || {}).value || "";
        var p2 = ($("setup-pass2") || {}).value || "";
        if (!u) return showErr("请填写用户名");
        if (!p || p.length < 6) return showErr("密码至少 6 位");
        if (p !== p2) return showErr("两次密码不一致");
        post("/api/auth/setup", { username: u, password: p }).then(function (res) {
          if (!res.ok) return showErr((res.data && res.data.detail) || "创建失败");
          if (res.data && res.data.recovery_code) {
            alert("请保存恢复码：\n" + res.data.recovery_code);
          }
          location.reload();
        }).catch(function (e) { showErr(String(e)); });
      };
      window.doLogin = function () {
        var u = (($("login-user") || {}).value || "").trim();
        var p = ($("login-pass") || {}).value || "";
        if (!u || !p) return showErr("请输入用户名和密码");
        post("/api/auth/login", { username: u, password: p }).then(function (res) {
          if (!res.ok) return showErr((res.data && res.data.detail) || "登录失败");
          location.reload();
        }).catch(function (e) { showErr(String(e)); });
      };
    })();
  </script>
'''

t2 = re.sub(
    r'<script id="inline-auth-fallback">[\s\S]*?</script>',
    new_script.strip(),
    t,
    count=1,
)
if t2 == t:
    # 无旧脚本则插入
    t2 = t.replace('<script src="/admin.js', new_script + '  <script src="/admin.js', 1)
t = t2
h.write_text(t, encoding="utf-8")
print("inline switcher ok")
