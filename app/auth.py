"""账号密码鉴权：首设建档、登录会话（HMAC 签名 Token）、改密、恢复码重置。

凭据存 data/auth.json（PBKDF2 哈希 + 恢复码哈希 + 签名密钥），不存明文。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from fastapi import Cookie, Header, HTTPException, Response, status

from .config import settings

AUTH_FILE_NAME = "auth.json"
SESSION_COOKIE = "ainovel_session"
TOKEN_TTL_SEC = 7 * 24 * 3600
_PBKDF2_ITER = 200_000

# 登录/重置失败限流（进程内即可，个人服务场景够用）
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SEC = 300
_fail_lock = threading.Lock()
_fail_map: dict[str, dict] = {}


def auth_path() -> Path:
    settings.ensure_dirs()
    return settings.database_path.parent / AUTH_FILE_NAME


def login_client_key(client_host: str | None, username: str = "") -> str:
    """限流键：优先 IP，叠加用户名，避免同机多账号互不影响。"""
    return f"{client_host or 'unknown'}|{(username or '').strip().lower()}"


def check_login_allowed(key: str) -> None:
    """连续失败达上限则短暂锁定，超出返回 429。"""
    now = time.time()
    with _fail_lock:
        rec = _fail_map.get(key)
        if rec and rec.get("until", 0) > now:
            wait = int(rec["until"] - now) + 1
            raise HTTPException(status_code=429, detail=f"尝试过于频繁，请 {wait} 秒后再试")


def note_login_failure(key: str) -> None:
    now = time.time()
    with _fail_lock:
        rec = _fail_map.setdefault(key, {"n": 0, "until": 0.0})
        # 锁定结束后重新计数
        if rec.get("until", 0) > now:
            return
        rec["until"] = 0.0
        rec["n"] = int(rec.get("n", 0)) + 1
        if rec["n"] >= LOGIN_MAX_FAIL:
            rec["until"] = now + LOGIN_LOCK_SEC
            rec["n"] = 0


def note_login_success(key: str) -> None:
    with _fail_lock:
        _fail_map.pop(key, None)


def load_auth() -> dict | None:
    path = auth_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("username") or not data.get("password_hash") or not data.get("secret"):
        return None
    return data


def save_auth(data: dict) -> None:
    path = auth_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def is_setup_required() -> bool:
    return load_auth() is None


def _hash_password(password: str, salt_hex: str | None = None, iterations: int = _PBKDF2_ITER) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iter_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def hash_recovery(code: str) -> str:
    return _hash_password(code)


def verify_recovery(code: str, stored: str | None) -> bool:
    if not stored:
        return False
    return verify_password(code, stored)


def generate_recovery_code() -> str:
    # 便于手抄：分组显示
    raw = secrets.token_hex(8).upper()
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def create_account(username: str, password: str) -> str:
    """首次设置账号，返回一次性恢复码。"""
    username = (username or "").strip()
    if not username or len(username) > 64:
        raise HTTPException(400, "用户名无效")
    if not password or len(password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if load_auth() is not None:
        raise HTTPException(409, "账号已存在，请直接登录")
    recovery = generate_recovery_code()
    data = {
        "username": username,
        "password_hash": _hash_password(password),
        "recovery_hash": hash_recovery(recovery),
        "secret": secrets.token_hex(32),
        "created_at": int(time.time()),
    }
    save_auth(data)
    return recovery


def change_password(username: str, old_password: str, new_password: str) -> None:
    data = load_auth()
    if not data:
        raise HTTPException(400, "尚未设置账号")
    if username != data["username"] or not verify_password(old_password, data["password_hash"]):
        raise HTTPException(401, "原用户名或密码错误")
    if not new_password or len(new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    data["password_hash"] = _hash_password(new_password)
    # 轮换签名密钥，改密后旧会话全部失效
    data["secret"] = secrets.token_hex(32)
    save_auth(data)


def reset_with_recovery(recovery_code: str, new_username: str, new_password: str) -> str:
    """恢复码重置账号，返回新的一次性恢复码（直接返回，避免共享状态）。"""
    data = load_auth()
    if not data:
        raise HTTPException(400, "尚未设置账号")
    if not verify_recovery((recovery_code or "").strip(), data.get("recovery_hash")):
        raise HTTPException(401, "恢复码无效")
    username = (new_username or "").strip() or data["username"]
    if not new_password or len(new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    data["username"] = username
    data["password_hash"] = _hash_password(new_password)
    # 重置后轮换恢复码，旧恢复码作废
    recovery = generate_recovery_code()
    data["recovery_hash"] = hash_recovery(recovery)
    data["secret"] = secrets.token_hex(32)  # 轮换密钥，旧会话失效
    save_auth(data)
    return recovery


def login(username: str, password: str) -> dict:
    data = load_auth()
    if not data:
        raise HTTPException(400, "尚未设置账号，请先完成初始化")
    if not hmac.compare_digest(username or "", data["username"]) or not verify_password(
        password or "", data["password_hash"]
    ):
        raise HTTPException(401, "用户名或密码错误")
    token = create_token(data)
    return {
        "username": data["username"],
        "token": token,
        "expires_in": TOKEN_TTL_SEC,
    }


def create_token(data: dict) -> str:
    exp = int(time.time()) + TOKEN_TTL_SEC
    payload = f"{data['username']}:{exp}".encode("utf-8")
    sig = hmac.new(data["secret"].encode("ascii"), payload, hashlib.sha256).digest()
    raw = payload + b"." + sig
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_token(token: str | None) -> str:
    """成功返回用户名，失败抛 401。"""
    data = load_auth()
    if not data:
        raise HTTPException(401, "尚未设置账号")
    if not token:
        raise HTTPException(401, "未登录")
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload, sig = raw.split(b".", 1)
        expect = hmac.new(data["secret"].encode("ascii"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expect):
            raise HTTPException(401, "登录已失效，请重新登录")
        user_s, exp_s = payload.decode("utf-8").split(":", 1)
        if int(exp_s) < time.time():
            raise HTTPException(401, "登录已过期，请重新登录")
        if not hmac.compare_digest(user_s, data["username"]):
            raise HTTPException(401, "登录已失效，请重新登录")
        return user_s
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "登录已失效，请重新登录") from exc


def extract_token(
    authorization: str | None = None,
    x_session_token: str | None = None,
    ainovel_session: str | None = None,
) -> str | None:
    """从 Header / Cookie 提取会话 Token（供 Depends 与手动调用共用）。"""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_session_token:
        return x_session_token.strip()
    return ainovel_session


def require_admin(token: str) -> str:
    """显式传入 Token 时校验并返回用户名；请勿无参调用（拿不到请求头）。"""
    if not token:
        raise HTTPException(401, "未登录")
    return verify_token(token)


def require_admin_dep(
    authorization: str | None = Header(default=None),
    x_session_token: str | None = Header(default=None),
    ainovel_session: str | None = Cookie(default=None),
) -> str:
    token = extract_token(authorization, x_session_token, ainovel_session)
    return verify_token(token)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=TOKEN_TTL_SEC,
        httponly=True,
        samesite="lax",
        # HTTPS 部署时由配置打开，防止明文 HTTP 泄露
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def reset_account_cli(new_username: str = "admin", new_password: str = "") -> str:
    """服务端紧急重置（reset_auth.py）。返回新恢复码。"""
    recovery = generate_recovery_code()
    data = {
        "username": new_username,
        "password_hash": _hash_password(new_password or secrets.token_urlsafe(12)),
        "recovery_hash": hash_recovery(recovery),
        "secret": secrets.token_hex(32),
        "created_at": int(time.time()),
        "reset_at": int(time.time()),
    }
    save_auth(data)
    return recovery
