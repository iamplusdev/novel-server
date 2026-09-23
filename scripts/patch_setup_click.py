from pathlib import Path

h = Path("index.html")
t = h.read_text(encoding="utf-8")
t = t.replace(
    '<button type="button" id="setup-btn" class="btn btn-primary btn-block">创建账号并进入</button>',
    '<button type="button" id="setup-btn" class="btn btn-primary btn-block" onclick="window.doSetup&&window.doSetup()">创建账号并进入</button>',
)
t = t.replace(
    '<button type="button" id="login-btn" class="btn btn-primary btn-block">登录</button>',
    '<button type="button" id="login-btn" class="btn btn-primary btn-block" onclick="window.doLogin&&window.doLogin()">登录</button>',
)
h.write_text(t, encoding="utf-8")

j = Path("admin.js")
s = j.read_text(encoding="utf-8")
# setupAccount 防空
s = s.replace(
    """  async function setupAccount() {
    const username = els.setupUser.value.trim();
    const password = els.setupPass.value;
    const password2 = els.setupPass2.value;""",
    """  async function setupAccount() {
    try {
    const username = (els.setupUser && els.setupUser.value || "").trim();
    const password = (els.setupPass && els.setupPass.value) || "";
    const password2 = (els.setupPass2 && els.setupPass2.value) || "";""",
    1,
)
# 在 setupAccount 的 catch 后闭合外层 try：找 setupAccount 结尾
if "async function setupAccount()" in s and "window.doSetup" not in s:
    s = s.replace(
        "  // Boot",
        "  window.doSetup = setupAccount;\n  window.doLogin = login;\n\n  // Boot",
        1,
    )
    print("exported handlers")

# 保证 setupAccount 内层 catch 之后有外层 catch
s = s.replace(
    """    } catch (err) {
      authError(err.message || "创建失败");
    }
  }""",
    """    } catch (err) {
      authError(err.message || "创建失败");
    }
    } catch (e) {
      authError(e.message || "创建失败");
    }
  }""",
    1,
)

j.write_text(s, encoding="utf-8")
print("paren", s.count("("), s.count(")"), "brace", s.count("{"), s.count("}"))
