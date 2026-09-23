"""账号 / 登录 / 改密 / 忘记密码 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth as auth_mod

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class ForgotIn(BaseModel):
    recovery_code: str = Field(..., min_length=4, max_length=64)
    username: str | None = Field(default=None, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=128)


@router.get("/status")
def auth_status() -> dict:
    data = auth_mod.load_auth()
    return {
        "setup_required": data is None,
        "username": data["username"] if data else None,
        "password_login": True,
    }


@router.post("/setup")
def auth_setup(payload: SetupIn, response: Response) -> dict:
    recovery = auth_mod.create_account(payload.username, payload.password)
    session = auth_mod.login(payload.username, payload.password)
    auth_mod.set_session_cookie(response, session["token"])
    return {
        "ok": True,
        "username": session["username"],
        "token": session["token"],
        "expires_in": session["expires_in"],
        "recovery_code": recovery,
    }


@router.post("/login")
def auth_login(payload: LoginIn, response: Response, request: Request) -> dict:
    # 登录失败限流：按 IP+用户名 计数
    key = auth_mod.login_client_key(
        request.client.host if request.client else None, payload.username
    )
    auth_mod.check_login_allowed(key)
    try:
        session = auth_mod.login(payload.username, payload.password)
    except HTTPException:
        auth_mod.note_login_failure(key)
        raise
    auth_mod.note_login_success(key)
    auth_mod.set_session_cookie(response, session["token"])
    return {"ok": True, **session}


@router.post("/logout")
def auth_logout(response: Response) -> dict:
    auth_mod.clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def auth_me(user: str = Depends(auth_mod.require_admin_dep)) -> dict:
    return {"username": user}


@router.post("/change-password")
def auth_change_password(
    payload: ChangePasswordIn,
    response: Response,
    user: str = Depends(auth_mod.require_admin_dep),
) -> dict:
    data = auth_mod.load_auth()
    if not data:
        raise HTTPException(400, "尚未设置账号")
    auth_mod.change_password(user, payload.old_password, payload.new_password)
    # 改密会轮换 secret，旧 Token 立即失效；这里换发新会话
    session = auth_mod.login(user, payload.new_password)
    auth_mod.set_session_cookie(response, session["token"])
    return {"ok": True, "username": user, "token": session["token"], "expires_in": session["expires_in"]}


@router.post("/forgot")
def auth_forgot(payload: ForgotIn, response: Response, request: Request) -> dict:
    # 恢复码重置同样限流，防止爆破
    key = auth_mod.login_client_key(
        request.client.host if request.client else None, payload.username or "forgot"
    )
    auth_mod.check_login_allowed(key)
    try:
        auth_mod.reset_with_recovery(
            payload.recovery_code,
            payload.username or "",
            payload.new_password,
        )
    except HTTPException:
        auth_mod.note_login_failure(key)
        raise
    auth_mod.note_login_success(key)
    new_code = auth_mod.get_new_recovery_code()
    data = auth_mod.load_auth()
    session = auth_mod.login(data["username"], payload.new_password)
    auth_mod.set_session_cookie(response, session["token"])
    return {
        "ok": True,
        "username": session["username"],
        "token": session["token"],
        "recovery_code": new_code,
    }
