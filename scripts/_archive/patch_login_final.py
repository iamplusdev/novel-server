from pathlib import Path

j = Path("admin.js")
s = j.read_text(encoding="utf-8")
# 导出更稳妥的登录/创建：异常必定提示
s = s.replace(
    "  window.doSetup = setupAccount;\n  window.doLogin = login;",
    "  window.doSetup = function () { return Promise.resolve(setupAccount()).catch(function (e) { authError(e.message || '创建失败'); }); };\n  window.doLogin = function () { return Promise.resolve(login()).catch(function (e) { authError(e.message || '登录失败'); }); };",
    1,
)
# afterLogin 失败也不挡进入后台
s = s.replace(
    """      if (els.loginPass) els.loginPass.value = "";
      showApp();
      await afterLogin();""",
    """      if (els.loginPass) els.loginPass.value = "";
      showApp();
      try { await afterLogin(); } catch (e) { toast(e.message || '加载数据失败', 'err'); }""",
    1,
)
j.write_text(s, encoding="utf-8")
print("ok", s.count("("), s.count(")"), s.count("{"), s.count("}"))
