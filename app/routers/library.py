"""书库体检 API：重复合并、损坏 TXT 修复。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_admin_dep
from ..database import get_db
from ..library_check import (
    find_duplicate_groups,
    merge_duplicates,
    repair_book,
    repair_books,
    relocate_books,
    scan_issues,
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


class RelocateIn(BaseModel):
    """按分类归位：可选仅处理指定书，缺省全库。"""
    book_ids: list[int] | None = None


@router.get("/report")
def library_report(db: Session = Depends(get_db)) -> dict:
    dups = find_duplicate_groups(db)
    issues = scan_issues(db)
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
    }


@router.post("/merge")
def library_merge(payload: MergeIn, db: Session = Depends(get_db)) -> dict:
    try:
        return merge_duplicates(db, payload.keep_id, payload.delete_ids)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/repair")
def library_repair(payload: RepairIn, db: Session = Depends(get_db)) -> dict:
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
    """按书籍分类把源 TXT 归位到对应分类文件夹（本地 + WebDAV）。"""
    book_ids = payload.book_ids if payload else None
    return relocate_books(db, book_ids)
