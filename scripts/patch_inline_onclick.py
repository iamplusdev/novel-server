from pathlib import Path

h = Path("index.html")
t = h.read_text(encoding="utf-8")

login_onclick = (
    "onclick=\"(function(){var u=(document.getElementById('login-user')||{}).value||'';"
    "var p=(document.getElementById('login-pass')||{}).value||'';"
    "u=u.trim(); if(!u||!p){var e=document.getElementById('login-error');"
    "if(e){e.hidden=false;e.textContent='请输入用户名和密码'} return;}"
    "fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({username:u,password:p})})"
    ".then(function(r){return r.text().then(function(txt){var j=null;"
    "try{j=txt?JSON.parse(txt):null}catch(err){j={detail:txt}};"
    "return {ok:r.ok,j:j}})})"
    ".then(function(res){ if(!res.ok){var e=document.getElementById('login-error');"
    "if(e){e.hidden=false;e.textContent=(res.j&&res.j.detail)||'登录失败'} return;}"
    "if(res.j&&res.j.token){try{localStorage.setItem('novel_admin_token',res.j.token)}catch(err){}}"
    "location.reload(); })"
    ".catch(function(err){var e=document.getElementById('login-error');"
    "if(e){e.hidden=false;e.textContent=String(err)}});})()\""
)

setup_onclick = (
    "onclick=\"(function(){var u=(document.getElementById('setup-user')||{}).value||'';"
    "var p=(document.getElementById('setup-pass')||{}).value||'';"
    "var p2=(document.getElementById('setup-pass2')||{}).value||'';"
    "u=u.trim(); var er=document.getElementById('login-error');"
    "function msg(m){if(er){er.hidden=false;er.textContent=m}}"
    "if(!u) return msg('请填写用户名');"
    "if(!p||p.length<6) return msg('密码至少 6 位');"
    "if(p!==p2) return msg('两次密码不一致');"
    "fetch('/api/auth/setup',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({username:u,password:p})})"
    ".then(function(r){return r.text().then(function(txt){var j=null;"
    "try{j=txt?JSON.parse(txt):null}catch(err){j={detail:txt}};"
    "return {ok:r.ok,j:j}})})"
    ".then(function(res){ if(!res.ok){msg((res.j&&res.j.detail)||'创建失败'); return;}"
    "if(res.j&&res.j.token){try{localStorage.setItem('novel_admin_token',res.j.token)}catch(err){}}"
    "if(res.j&&res.j.recovery_code){alert('请保存恢复码：\\n'+res.j.recovery_code)}"
    "location.reload(); })"
    ".catch(function(err){msg(String(err))});})()\""
)

import re
t = re.sub(
    r'<button[^>]*id="login-btn"[^>]*>登录</button>',
    f'<button type="button" id="login-btn" class="btn btn-primary btn-block" {login_onclick}>登录</button>',
    t,
    count=1,
)
t = re.sub(
    r'<button[^>]*id="setup-btn"[^>]*>创建账号并进入</button>',
    f'<button type="button" id="setup-btn" class="btn btn-primary btn-block" {setup_onclick}>创建账号并进入</button>',
    t,
    count=1,
)
h.write_text(t, encoding="utf-8")
print("login onclick", "api/auth/login" in t and 'id="login-btn"' in t)
print("setup onclick", "api/auth/setup" in t and 'id="setup-btn"' in t)
