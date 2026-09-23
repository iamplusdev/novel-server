"""SQLAlchemy 引擎与会话。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings.ensure_dirs()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_books()


def _migrate_books() -> None:
    """给已有库补上刮削来源字段。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(books)")).fetchall()
        cols = {r[1] for r in rows}
        if "source" not in cols:
            conn.execute(text("ALTER TABLE books ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT ''"))
        if "source_id" not in cols:
            conn.execute(text("ALTER TABLE books ADD COLUMN source_id VARCHAR(64) NOT NULL DEFAULT ''"))
        conn.commit()


def dispose_engine() -> None:
    """还原备份时关闭连接并释放引擎。"""
    engine.dispose()


def reset_database() -> None:
    """替换 novels.db 文件后重建引擎与会话工厂。"""
    global engine, SessionLocal
    engine.dispose()
    engine = _make_engine()
    SessionLocal.configure(bind=engine)
    init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def escape_like(text: str) -> str:
    """转义 SQL LIKE 通配符，避免用户输入改变匹配语义。配合 like(..., escape='\\\\')。"""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
