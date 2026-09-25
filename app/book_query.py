"""书籍列表查询构造：公开 API 与管理端共用，避免筛选/排序逻辑两处漂移。"""
from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .config import parse_category_label
from .database import escape_like, fts_available
from .models import Book


def _like_filters(q: str, *, with_intro: bool):
    like = f"%{escape_like(q)}%"
    cols = [Book.title, Book.author, Book.tags]
    if with_intro:
        cols.append(Book.intro)
    return [c.like(like, escape="\\") for c in cols]


def apply_search(stmt, db: Session, q: str | None, *, with_intro: bool = True):
    """关键词搜索：FTS 优先，无命中或不可用时回退 LIKE。"""
    if not q:
        return stmt
    q = q.strip()
    if not q:
        return stmt
    if fts_available():
        from .database import fts_search_ids

        fts_ids = fts_search_ids(db, q)
        if fts_ids:
            return stmt.where(Book.id.in_(fts_ids))
        # FTS 无命中时也做 LIKE 兜底（拼音/部分词）
    return stmt.where(or_(*_like_filters(q, with_intro=with_intro)))


def apply_tag(stmt, tag: str | None):
    if not tag:
        return stmt
    tag = tag.strip()
    if not tag:
        return stmt
    return stmt.where(
        or_(
            Book.tags == tag,
            Book.tags.like(f"{tag},%", escape="\\"),
            Book.tags.like(f"%,{tag}", escape="\\"),
            Book.tags.like(f"%,{tag},%", escape="\\"),
        )
    )


def apply_source_category(
    stmt,
    *,
    source: str | None = None,
    category: str | None = None,
):
    """书源 + 分类筛选：支持「起点」「都市」「起点-都市」等组合。"""
    src_raw = (source or "").strip()
    cat_raw = (category or "").strip()
    if cat_raw:
        psrc, pure = parse_category_label(cat_raw)
        if psrc:
            src_raw = src_raw or psrc
            cat_raw = pure or cat_raw
        else:
            cat_raw = pure or cat_raw
    if src_raw in ("本地", "none", "-"):
        stmt = stmt.where(
            ~Book.category.like("起点-%", escape="\\"),
            ~Book.category.like("番茄-%", escape="\\"),
        )
    elif src_raw in ("起点", "番茄"):
        stmt = stmt.where(
            or_(Book.category.startswith(f"{src_raw}-"), Book.source == src_raw)
        )
    if cat_raw and cat_raw != "全部":
        if src_raw in ("起点", "番茄"):
            label = f"{src_raw}-{cat_raw}"
            stmt = stmt.where(
                or_(
                    Book.category == label,
                    Book.category == cat_raw,
                    and_(
                        Book.category.startswith(f"{src_raw}-"),
                        Book.category.endswith(f"-{cat_raw}"),
                    ),
                    and_(Book.source == src_raw, Book.category == cat_raw),
                )
            )
        else:
            stmt = stmt.where(
                or_(Book.category == cat_raw, Book.category.endswith(f"-{cat_raw}"))
            )
    return stmt


def apply_sort(stmt, sort: str):
    if sort == "title":
        return stmt.order_by(Book.title.asc(), Book.id.asc())
    if sort == "author":
        return stmt.order_by(Book.author.asc(), Book.title.asc())
    if sort == "words":
        return stmt.order_by(Book.word_count.desc(), Book.title.asc())
    if sort == "chapters":
        return stmt.order_by(Book.chapter_count.desc(), Book.title.asc())
    return stmt.order_by(Book.updated_at.desc(), Book.id.desc())


def build_books_stmt(
    db: Session,
    *,
    category: str | None = None,
    q: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    sort: str = "updated",
    with_intro_search: bool = True,
):
    """组装筛选后的 select(Book)，不含分页。"""
    stmt = select(Book)
    stmt = apply_source_category(stmt, source=source, category=category)
    if status:
        stmt = stmt.where(Book.status == status)
    stmt = apply_tag(stmt, tag)
    stmt = apply_search(stmt, db, q, with_intro=with_intro_search)
    return apply_sort(stmt, sort)


def count_books(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
