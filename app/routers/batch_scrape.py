"""批量刮削 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import require_admin_dep
from ..batch_scrape import get_batch_status, request_batch_cancel, score_match, start_batch_scrape

router = APIRouter(
    prefix="/api/admin/scrape/batch",
    tags=["batch-scrape"],
    dependencies=[Depends(require_admin_dep)],
)


class BatchIn(BaseModel):
    # all=按起点→番茄→纵横顺序，命中即停；也可指定单一书源
    source: str = Field(default="all", max_length=20)
    only_missing: bool = True
    min_score: float = Field(default=0.8, ge=0.3, le=1.0)
    limit: int | None = Field(default=None, ge=1, le=5000)
    # 非空时只刮削指定书（书库多选批量刮削）；为空则按 only_missing 扫全库
    book_ids: list[int] | None = Field(default=None, max_length=500)
    # 取数方式：api / chrome / auto
    mode: str = Field(default="auto", max_length=20)


class ScoreIn(BaseModel):
    local_title: str
    local_author: str = ""
    hit_title: str
    hit_author: str = ""


@router.post("/start")
def batch_start(payload: BatchIn) -> dict:
    started = start_batch_scrape(
        source=payload.source,
        only_missing=payload.only_missing,
        min_score=payload.min_score,
        limit=payload.limit,
        book_ids=payload.book_ids or None,
        mode=payload.mode,
    )
    return {"started": started, "status": get_batch_status()}


@router.get("/status")
def batch_status() -> dict:
    return get_batch_status()


@router.post("/cancel")
def batch_cancel() -> dict:
    """请求停止批量刮削（A6）。"""
    ok = request_batch_cancel()
    return {"ok": ok, "status": get_batch_status()}


@router.post("/score")
def batch_score(payload: ScoreIn) -> dict:
    return {
        "score": score_match(
            payload.local_title, payload.local_author, payload.hit_title, payload.hit_author
        )
    }
