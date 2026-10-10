"""书库体检 API：重复合并、损坏 TXT 修复、后台扫描（含进度）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..database import get_db
from ..library_check import (
    find_duplicate_groups,
    get_scan_status,
    merge_duplicates,
    relocate_books,
    repair_book,
    repair_books,
    request_scan_cancel,
    scan_issues,
    start_library_scan,
)

router = APIRouter(
    prefix="/api/admin/library",
    tags=["library-check"],
    dependencies=[Depends(require_admin_dep)],
)


class MergeIn(BaseModel):
    keep_id: int
    delete_ids: list[int] = Field(..., min_length=1)


class RepairIn(BaseModel):
    book_ids: list[int] | None = None
    mode: str = Field(default="auto", pattern="^(auto|clean|reparse)$")
    # 未显式给 book_ids 时，需显式允许才做全库修复，避免隐式全库深扫
    allow_full_scan: bool = False


class RelocateIn(BaseModel):
    """按分类归位：可选仅处理指定书，缺省全库。"""

    book_ids: list[int] | None = None


class ScanIn(BaseModel):
    deep: bool = False


@router.get("/report")
def library_report(deep: bool = False, db: Session = Depends(get_db)) -> dict:
    """同步体检报告（deep=false 快速 SQL；deep=true 含正文乱码/控制符，较慢）。

    大库深度体检建议改用后台扫描（POST /scan + /scan/stream）以免阻塞。
    """
    dups = find_duplicate_groups(db)
    issues = scan_issues(db, deep=deep)
    return {
        "duplicates": dups,
        "issues": [
            {
                "book_id": i.book_id,
                "title": i.title,
                "kind": i.kind,
                "message": i.message,
                "detail": i.detail,
            }
            for i in issues
        ],
        "duplicate_groups": len(dups),
        "issue_count": len(issues),
        "deep": deep,
    }


def _sse_pack(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/scan")
def library_scan_start(payload: ScanIn) -> dict:
    """启动后台体检（重复 + 异常），返回是否已开始。"""
    started = start_library_scan(payload.deep)
    return {"started": started, "status": get_scan_status()}


@router.get("/scan/status")
def library_scan_status() -> dict:
    return get_scan_status()


@router.post("/scan/cancel")
def library_scan_cancel() -> dict:
    """请求中止后台体检。"""
    ok = request_scan_cancel()
    return {"ok": ok, "status": get_scan_status()}


@router.get("/scan/stream")
async def library_scan_stream(request: Request):
    """后台体检进度 SSE：直到结束/断开，结束时的消息带 report。"""
    import asyncio

    async def gen():
        while True:
            if await request.is_disconnected():
                break
            st = get_scan_status()
            yield _sse_pack(st)
            if not st.get("running"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/merge")
def library_merge(payload: MergeIn, db: Session = Depends(get_db)) -> dict:
    try:
        return merge_duplicates(db, payload.keep_id, payload.delete_ids)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/repair")
def library_repair(payload: RepairIn, db: Session = Depends(get_db)) -> dict:
    if payload.book_ids is None and not payload.allow_full_scan:
        raise HTTPException(400, "请显式指定 book_ids；如需全库修复请传 allow_full_scan=true")
    results = repair_books(db, payload.book_ids, mode=payload.mode)
    return {"results": results, "count": len(results)}


@router.post("/repair/{book_id}")
def library_repair_one(book_id: int, mode: str = "auto", db: Session = Depends(get_db)) -> dict:
    try:
        return repair_book(db, book_id, mode=mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/relocate")
def library_relocate(payload: RelocateIn | None = None, db: Session = Depends(get_db)) -> dict:
    """按书籍分类把源 TXT 归位到对应分类文件夹（本地）。"""
    book_ids = payload.book_ids if payload else None
    return relocate_books(db, book_ids)
