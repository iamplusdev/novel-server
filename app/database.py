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
    _init_fts()


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


def _init_fts() -> None:
    """书籍全文检索（A9）：FTS5 外部内容表 + 触发器同步；失败则仅用 LIKE。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        try:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
                        title, author, tags, intro,
                        content='books', content_rowid='id',
                        tokenize='unicode61'
                    )
                    """
                )
            )
            # 增量同步触发器
            for name, sql in (
                (
                    "books_ai_fts",
                    "CREATE TRIGGER IF NOT EXISTS books_ai_fts AFTER INSERT ON books BEGIN "
                    "INSERT INTO books_fts(rowid, title, author, tags, intro) "
                    "VALUES (new.id, new.title, new.author, new.tags, new.intro); END",
                ),
                (
                    "books_ad_fts",
                    "CREATE TRIGGER IF NOT EXISTS books_ad_fts AFTER DELETE ON books BEGIN "
                    "INSERT INTO books_fts(books_fts, rowid, title, author, tags, intro) "
                    "VALUES ('delete', old.id, old.title, old.author, old.tags, old.intro); END",
                ),
                (
                    "books_au_fts",
                    "CREATE TRIGGER IF NOT EXISTS books_au_fts AFTER UPDATE ON books BEGIN "
                    "INSERT INTO books_fts(books_fts, rowid, title, author, tags, intro) "
                    "VALUES ('delete', old.id, old.title, old.author, old.tags, old.intro); "
                    "INSERT INTO books_fts(rowid, title, author, tags, intro) "
                    "VALUES (new.id, new.title, new.author, new.tags, new.intro); END",
                ),
            ):
                conn.execute(text(sql))
            # 首次建表后按需重建索引（书籍有、FTS 空时）
            n_fts = conn.execute(text("SELECT count(*) FROM books_fts")).scalar() or 0
            n_books = conn.execute(text("SELECT count(*) FROM books")).scalar() or 0
            if n_books and not n_fts:
                conn.execute(text("INSERT INTO books_fts(books_fts) VALUES('rebuild')"))
            conn.commit()
        except Exception:  # noqa: BLE001
            # 无 FTS5 的构建则自动降级为 LIKE
            conn.rollback()


def fts_available() -> bool:
    """当前库是否启用了 books_fts。"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM books_fts LIMIT 1"))
            return True
    except Exception:  # noqa: BLE001
        return False


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
