from pathlib import Path

p = Path("admin.js")
t = p.read_text(encoding="utf-8")

# bootAuth：首设时强制仅显示创建账号
old = """    if (st.setup_required) {
      showLogin();
      showAuthPane("setup");
      return;
    }"""
new = """    if (st.setup_required) {
      showLogin();
      showAuthPane("setup");
      if (els.authSubtitle) setText(els.authSubtitle, "首次使用 · 请创建管理账号");
      return;
    }"""
if old in t:
    t = t.replace(old, new, 1)
    print("boot setup hint")

# 登录失败：若提示尚未设置，切到 setup
old2 = """    } catch (err) {
      authError(err.message || "登录失败");
    }
  }

  async function setupAccount() {"""
new2 = """    } catch (err) {
      const msg = (err && err.message) || "登录失败";
      if (String(msg).indexOf("尚未设置") >= 0 || String(msg).indexOf("创建") >= 0) {
        showAuthPane("setup");
        authError("首次使用请先创建账号（下方表单）");
      } else {
        authError(msg);
      }
    }
  }

  async function setupAccount() {"""
if old2 in t:
    t = t.replace(old2, new2, 1)
    print("login fallback setup")
else:
    print("login catch miss")

p.write_text(t, encoding="utf-8")
print("paren", t.count("("), t.count(")"), "brace", t.count("{"), t.count("}"))
