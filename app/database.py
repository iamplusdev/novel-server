"""SQLAlchemy 引擎与会话。"""
from __future__ import annotations

from collections.abc import Generator, Sequence

from sqlalchemy import create_engine, delete, event, select, text
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
    _migrate_chapters_storage()
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


def _migrate_chapters_storage() -> None:
    """章节表补偏移列，并把遗留 content 正文迁到正文包后清空。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(chapters)")).fetchall()
        cols = {r[1] for r in rows}
        if "content_offset" not in cols:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN content_offset INTEGER NOT NULL DEFAULT 0"))
        if "content_length" not in cols:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN content_length INTEGER NOT NULL DEFAULT 0"))
        if "content_chars" not in cols:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN content_chars INTEGER NOT NULL DEFAULT 0"))
        conn.commit()
    _migrate_content_to_packs()


def _migrate_content_to_packs() -> None:
    """把仍在 chapters.content 的正文写入正文包，并按偏移回填后清空 content 列。"""
    from .content_store import write_pack
    from .models import Book, Chapter

    with SessionLocal() as db:
        # 仅处理仍带正文列的书（迁移后 content 为空字符串）
        book_ids = (
            db.execute(select(Chapter.book_id).where(Chapter.content != "").distinct())
            .scalars()
            .all()
        )
        for bid in book_ids:
            chapters = (
                db.execute(
                    select(Chapter).where(Chapter.book_id == bid).order_by(Chapter.index, Chapter.id)
                )
                .scalars()
                .all()
            )
            texts = [c.content or "" for c in chapters]
            spans = write_pack(bid, texts)
            for ch, (off, blen, clen) in zip(chapters, spans):
                ch.content_offset = off
                ch.content_length = blen
                ch.content_chars = clen
                ch.content = ""  # 清空遗留正文列，SQLite 文件在 VACUUM 后才真正收缩
            book = db.get(Book, bid)
            if book is not None:
                book.word_count = sum(clen for _o, _b, clen in spans)
            db.commit()
        # 有正文迁出时收缩库文件，回收原 content 列占用
        if book_ids:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("VACUUM"))


# FTS 删除同步触发器：索引与内容表不一致时会抛 database disk image is malformed
_FTS_AD_TRIGGER_SQL = (
    "CREATE TRIGGER IF NOT EXISTS books_ad_fts AFTER DELETE ON books BEGIN "
    "INSERT INTO books_fts(books_fts, rowid, title, author, tags, intro) "
    "VALUES ('delete', old.id, old.title, old.author, old.tags, old.intro); END"
)


def _init_fts() -> None:
    """书籍全文检索（A9）：FTS5 外部内容表 + 触发器同步；失败则仅用 LIKE。"""
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
                ("books_ad_fts", _FTS_AD_TRIGGER_SQL),
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
            # 书籍数与 FTS 不一致（含 FTS 为空/半同步）时重建，避免删除触发器报错
            n_fts = conn.execute(text("SELECT count(*) FROM books_fts")).scalar() or 0
            n_books = conn.execute(text("SELECT count(*) FROM books")).scalar() or 0
            if n_books != n_fts:
                conn.execute(text("INSERT INTO books_fts(books_fts) VALUES('rebuild')"))
            conn.commit()
        except Exception:  # noqa: BLE001
            # 无 FTS5 的构建则自动降级为 LIKE
            conn.rollback()


def rebuild_fts() -> None:
    """全量重建 books_fts 索引；无 FTS 时静默忽略。"""
    if not fts_available():
        return
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO books_fts(books_fts) VALUES('rebuild')"))


def delete_books_safe(db: Session, book_ids: Sequence[int]) -> bool:
    """安全删除书籍及其章节/正文包，返回是否走了 FTS 恢复路径。

    优先正常 DELETE 以触发 FTS 同步；若索引不同步导致触发器失败，
    则临时禁用删除触发器完成删除，再 rebuild 索引并恢复触发器。
    使用 Core 批量删除，避免 ORM 级联加载全部章节正文。
    """
    from .models import Book, Chapter  # 延迟导入，避免循环依赖

    ids = [int(i) for i in book_ids if i is not None]
    if not ids:
        return False

    def _wipe() -> None:
        # 先删章节再删书；与 FK ON DELETE CASCADE 双保险
        db.execute(delete(Chapter).where(Chapter.book_id.in_(ids)))
        db.execute(delete(Book).where(Book.id.in_(ids)))

    def _drop_packs() -> None:
        # 正文包随书删除，避免 data/contents 残留
        from .content_store import delete_pack

        for bid in ids:
            delete_pack(bid)

    try:
        _wipe()
        db.commit()
        _drop_packs()
        return False
    except Exception:
        db.rollback()
        if not fts_available():
            raise
        # FTS 不同步：禁用删除触发器后重试
        with engine.begin() as conn:
            conn.execute(text("DROP TRIGGER IF EXISTS books_ad_fts"))
        try:
            _wipe()
            db.commit()
            _drop_packs()
        except Exception:
            db.rollback()
            # 恢复触发器后原样抛出
            with engine.begin() as conn:
                conn.execute(text(_FTS_AD_TRIGGER_SQL))
            raise
        # 删除成功后重建索引并恢复触发器
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO books_fts(books_fts) VALUES('rebuild')"))
            conn.execute(text(_FTS_AD_TRIGGER_SQL))
        return True


# FTS 可用性缓存：库生命周期内只探测一次，避免每次搜索都查虚拟表
_fts_available: bool | None = None


def fts_available() -> bool:
    """当前库是否启用了 books_fts（结果缓存，reset_database 后失效）。"""
    global _fts_available
    if _fts_available is not None:
        return _fts_available
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM books_fts LIMIT 1"))
            _fts_available = True
    except Exception:  # noqa: BLE001
        _fts_available = False
    return _fts_available


def dispose_engine() -> None:
    """还原备份时关闭连接并释放引擎。"""
    engine.dispose()


def reset_database() -> None:
    """替换 novels.db 文件后重建引擎与会话工厂。"""
    global engine, SessionLocal, _fts_available
    engine.dispose()
    engine = _make_engine()
    SessionLocal.configure(bind=engine)
    _fts_available = None
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


def escape_fts_query(q: str) -> str:
    """FTS5 MATCH 安全短语：去掉引号后包成双引号短语，避免 * ^ NEAR 等语法误伤。"""
    cleaned = " ".join((q or "").replace('"', " ").split())
    return f'"{cleaned}"' if cleaned else ""


def fts_search_ids(db: Session, q: str) -> list[int] | None:
    """FTS 搜索返回 id 列表；无 FTS 或语法失败返回 None（调用方回退 LIKE）。"""
    if not fts_available():
        return None
    phrase = escape_fts_query(q)
    if not phrase:
        return None
    try:
        rows = db.execute(
            text("SELECT rowid FROM books_fts WHERE books_fts MATCH :q"),
            {"q": phrase},
        ).all()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return None
