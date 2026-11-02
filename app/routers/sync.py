"""阅读进度同步 API：WebDAV 配置 + 打开拉取 / 关闭推送。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import sync_progress, webdav_settings
from ..auth import require_admin_dep
from ..database import get_db

router = APIRouter(
    prefix="/api/admin", tags=["sync"], dependencies=[Depends(require_admin_dep)]
)


class WebDavSettingsIn(BaseModel):
    enabled: bool | None = None
    url: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    dir: str | None = Field(default=None, max_length=200)
    timeout: int | None = Field(default=None, ge=2, le=20)
    verify_tls: bool | None = None
    clear_password: bool = False


class PushIn(BaseModel):
    chapter_id: int
    # 章内估算字符位置；仅作 Legado 落点参考
    chapter_pos: int = Field(default=0, ge=0)
    client_time: int | None = Field(default=None, ge=0)


@router.get("/settings/webdav")
def get_webdav_settings() -> dict:
    return webdav_settings.public_dict()


@router.put("/settings/webdav")
def put_webdav_settings(payload: WebDavSettingsIn) -> dict:
    try:
        webdav_settings.update(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **webdav_settings.public_dict()}


@router.post("/settings/webdav/test")
def test_webdav() -> dict:
    try:
        return sync_progress.test_connection()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/books/{book_id}/sync/info")
def book_sync_info(book_id: int, db: Session = Depends(get_db)) -> dict:
    """详情页诊断：远程文件名、远端进度与章节匹配结果。"""
    try:
        return sync_progress.sync_info(db, book_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/books/{book_id}/sync/push-now")
def push_book_progress_now(book_id: int, chapter_id: int | None = None) -> dict:
    """手动推送本地当前进度（同步返回结果）。"""
    try:
        return sync_progress.push_now(book_id, chapter_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/books/{book_id}/sync/pull")
def pull_book_progress(book_id: int, db: Session = Depends(get_db)) -> dict:
    """打开阅读页时调用：远端更新则写入本地并返回目标章节。"""
    try:
        return sync_progress.pull_progress(db, book_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/books/{book_id}/sync/push")
def push_book_progress(
    book_id: int, payload: PushIn, background: BackgroundTasks
) -> dict:
    """关闭页面时调用：立即返回，后台写入 WebDAV。"""
    background.add_task(
        sync_progress.push_progress_bg,
        book_id,
        payload.chapter_id,
        payload.chapter_pos,
        payload.client_time,
    )
    return {"ok": True, "queued": True}
