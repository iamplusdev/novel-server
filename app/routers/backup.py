"""WebDAV 备份 / 还原管理 API（需 Admin Token）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_admin_dep
from ..backup import (
    get_status,
    list_remote_backups,
    load_config,
    restore_from_remote,
    run_backup,
    save_config,
    test_webdav,
    BackupConfig,
)
from ..webdav import WebDAVError

router = APIRouter(prefix="/api/admin/backup", tags=["backup"], dependencies=[Depends(require_admin_dep)])


class BackupConfigIn(BaseModel):
    webdav_url: str = Field(default="", max_length=500)
    username: str = Field(default="", max_length=100)
    password: str | None = Field(default=None, max_length=200)  # null 表示保持原密码
    remote_path: str = Field(default="novel-server-backups", max_length=200)
    auto_enabled: bool = False
    interval_hours: int = Field(default=24, ge=1, le=24 * 30)
    keep_count: int = Field(default=7, ge=1, le=100)


class RestoreIn(BaseModel):
    filename: str = Field(..., min_length=5, max_length=200)


class TestIn(BaseModel):
    webdav_url: str = ""
    username: str = ""
    password: str | None = None
    remote_path: str = "novel-server-backups"


@router.get("/config")
def get_backup_config() -> dict:
    return load_config().to_public_dict()


@router.put("/config")
def put_backup_config(payload: BackupConfigIn) -> dict:
    cfg = load_config()
    cfg.webdav_url = payload.webdav_url.strip()
    cfg.username = payload.username.strip()
    if payload.password is not None:
        cfg.password = payload.password
    cfg.remote_path = (payload.remote_path or "novel-server-backups").strip("/").replace("\\", "/") or "novel-server-backups"
    cfg.auto_enabled = payload.auto_enabled
    cfg.interval_hours = payload.interval_hours
    cfg.keep_count = payload.keep_count
    save_config(cfg)
    return cfg.to_public_dict()


@router.post("/test")
def post_test(payload: TestIn) -> dict:
    cfg = load_config()
    if payload.webdav_url:
        cfg.webdav_url = payload.webdav_url.strip()
    if payload.username is not None:
        cfg.username = payload.username.strip()
    if payload.password is not None:
        cfg.password = payload.password
    if payload.remote_path:
        cfg.remote_path = payload.remote_path.strip("/")
    try:
        msg = test_webdav(cfg)
        return {"ok": True, "message": msg}
    except WebDAVError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/run")
def post_run() -> dict:
    try:
        result = run_backup()
        return {"ok": True, **result, "status": get_status()}
    except WebDAVError as e:
        raise HTTPException(409 if "已有" in str(e) else 502, str(e)) from e


@router.get("/list")
def get_list() -> dict:
    try:
        return {"items": list_remote_backups(load_config())}
    except WebDAVError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/restore")
def post_restore(payload: RestoreIn) -> dict:
    try:
        result = restore_from_remote(payload.filename)
        return {"ok": True, **result}
    except WebDAVError as e:
        code = 409 if "已有" in str(e) else 502
        if "非法文件名" in str(e) or "缺少" in str(e):
            code = 400
        raise HTTPException(code, str(e)) from e


@router.get("/status")
def get_backup_status() -> dict:
    return get_status()
