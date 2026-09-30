"""清空旧书目数据（books 等表），保留 novels/ 源 TXT 与登录配置。

分类已统一为起点 15 类，旧 category/目录名不兼容，按约定直接清空重建。
注意：books_fts 是 FTS5 外部内容表，禁止 DELETE，删完内容表后 rebuild。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "novels.db"

# 只清内容表；FTS 虚拟表靠 rebuild 同步
_CONTENT_TABLES = ("chapters", "import_logs", "books")


def main() -> int:
    if not DB.is_file():
        print(f"数据库不存在: {DB}")
        return 0
    con = sqlite3.connect(DB)
    try:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        print(f"内容表清空: {', '.join(t for t in _CONTENT_TABLES if t in tables)}")
        con.execute("PRAGMA foreign_keys=OFF")
        for t in _CONTENT_TABLES:
            if t in tables:
                con.execute(f"DELETE FROM [{t}]")
        # FTS5 外部内容表：delete-all/rebuild，绝不能 DELETE FROM books_fts
        if "books_fts" in tables:
            try:
                con.execute("INSERT INTO books_fts(books_fts) VALUES('delete-all')")
            except sqlite3.Error:
                con.rollback()
            try:
                con.execute("INSERT INTO books_fts(books_fts) VALUES('rebuild')")
                print("books_fts 索引已 rebuild")
            except sqlite3.Error as e:
                print(f"books_fts rebuild 跳过: {e}")
        con.commit()
        left = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        print(f"完成。books 剩余 {left} 行。请重新导入/刮削。")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
