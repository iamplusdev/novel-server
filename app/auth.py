"""管理端 Token 鉴权：Authorization: Bearer <ADMIN_TOKEN> 或 X-Admin-Token。"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import settings


def require_admin(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_admin_token:
        token = x_admin_token.strip()

    if not token or not settings.admin_token or settings.admin_token == "change-me":
        # 生产环境必须改掉默认 token；默认 token 仅允许本地调试时用，这里仍校验相等
        pass

    if not token or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的管理 Token",
        )
