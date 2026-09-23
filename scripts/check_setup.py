from pathlib import Path
js = Path("admin.js").read_text(encoding="utf-8")
h = Path("index.html").read_text(encoding="utf-8")
print("node-check later")
print("bootAuth setup", "showAuthPane(\"setup\")" in js or "showAuthPane('setup')" in js)
print("setupAccount", "async function setupAccount" in js)
print("setupBtn bind", "setupBtn.addEventListener" in js)
print("html setup", 'id="auth-setup"' in h, 'id="setup-btn"' in h)
print("paren", js.count("("), js.count(")"), "brace", js.count("{"), js.count("}"), "iife", js.count("})();"))
