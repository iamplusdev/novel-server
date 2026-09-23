from pathlib import Path

h = Path("index.html")
t = h.read_text(encoding="utf-8")

# 紧跟登录/创建按钮的独立绑定脚本（不依赖 admin.js）
helper = r'''
<script id="auth-button-bind">
(function () {
  function bind(id, fn) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("click", fn);
  }
  function showErr(msg) {
    var el = document.getElementById("login-error");
    if (el) { el.hidden = false; el.textContent = msg || ""; }
  }
  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    }).then(function (r) {
      return r.text().then(function (txt) {
        var j = null;
        try { j = txt ? JSON.parse(txt) : null; } catch (e) { j = { detail: txt }; }
        return { ok: r.ok, j: j };
      });
    });
  }
  bind("setup-btn", function () {
    var u = (document.getElementById("setup-user").value || "").trim();
    var p = document.getElementById("setup-pass").value || "";
    var p2 = document.getElementById("setup-pass2").value || "";
    if (!u) return showErr("请填写用户名");
    if (!p || p.length < 6) return showErr("密码至少 6 位");
    if (p !== p2) return showErr("两次密码不一致");
    post("/api/auth/setup", { username: u, password: p }).then(function (res) {
      if (!res.ok) return showErr((res.j && res.j.detail) || "创建失败");
      if (res.j && res.j.token) localStorage.setItem("novel_admin_token", res.j.token);
      if (res.j && res.j.recovery_code) alert("请保存恢复码：\n" + res.j.recovery_code);
      location.reload();
    }).catch(function (e) { showErr(String(e)); });
  });
  bind("login-btn", function () {
    var u = (document.getElementById("login-user").value || "").trim();
    var p = document.getElementById("login-pass").value || "";
    if (!u || !p) return showErr("请输入用户名和密码");
    post("/api/auth/login", { username: u, password: p }).then(function (res) {
      if (!res.ok) return showErr((res.j && res.j.detail) || "登录失败");
      if (res.j && res.j.token) localStorage.setItem("novel_admin_token", res.j.token);
      location.reload();
    }).catch(function (e) { showErr(String(e)); });
  });
})();
</script>
'''

if "auth-button-bind" not in t:
    # 插到登录卡片结束之后、app 之前
    marker = '  <div id="app" class="app" hidden>'
    if marker in t:
        t = t.replace(marker, helper + "\n" + marker, 1)
    else:
        t = t.replace("</body>", helper + "\n</body>", 1)

# 按钮改为 type=button，去掉可能冲突的 onclick
t = t.replace(
    '<button type="button" id="login-btn" class="btn btn-primary btn-block" onclick="window.doLogin&&window.doLogin()">登录</button>',
    '<button type="button" id="login-btn" class="btn btn-primary btn-block">登录</button>',
)
t = t.replace(
    '<button type="button" id="setup-btn" class="btn btn-primary btn-block" onclick="window.doSetup&&window.doSetup()">创建账号并进入</button>',
    '<button type="button" id="setup-btn" class="btn btn-primary btn-block">创建账号并进入</button>',
)

h.write_text(t, encoding="utf-8")
print("bind script", "auth-button-bind" in t)
