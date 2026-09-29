"""关键路径回归测试（D2）：鉴权 / 转义 / 封面 / FTS / 备份加密 / 导入取消。

兼容 `python -m unittest tests.test_core` 与 `pytest tests/test_core.py`。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        os.environ["DATABASE_PATH"] = str(self._tmp / "t.db")
        os.environ["NOVELS_DIR"] = str(self._tmp / "novels")
        os.environ["COVERS_DIR"] = str(self._tmp / "covers")
        os.environ["COOKIE_SECURE"] = "1"

        from app import config as cfg
        from app import database as dbmod

        # 直接改 settings 并重建引擎，避免 reload 造成表重复定义
        cfg.settings.database_path = self._tmp / "t.db"
        cfg.settings.novels_dir = self._tmp / "novels"
        cfg.settings.covers_dir = self._tmp / "covers"
        cfg.settings.database_url = f"sqlite:///{cfg.settings.database_path}"
        cfg.settings.cookie_secure = True
        cfg.settings.ensure_dirs()
        dbmod.reset_database()
        dbmod.init_db()
        self.db = dbmod
        self.cfg = cfg

    def test_escape_like(self) -> None:
        from app.database import escape_like

        self.assertEqual(escape_like("a%b"), "a\\%b")
        self.assertEqual(escape_like("a_b"), "a\\_b")
        self.assertEqual(escape_like("100%"), "100\\%")

    def test_cover_magic(self) -> None:
        from app.routers.admin import _detect_image_ext

        self.assertEqual(_detect_image_ext(b"\xff\xd8\xff"), ".jpg")
        self.assertEqual(_detect_image_ext(b"\x89PNG\r\n\x1a\n"), ".png")
        self.assertEqual(_detect_image_ext(b"GIF89a"), ".gif")
        self.assertEqual(_detect_image_ext(b"RIFF....WEBP"), ".webp")
        self.assertIsNone(_detect_image_ext(b"nope"))

    def test_login_rate_limit(self) -> None:
        from app import auth as auth_mod

        k = auth_mod.login_client_key("1.2.3.4", "admin")
        for _ in range(auth_mod.LOGIN_MAX_FAIL):
            auth_mod.note_login_failure(k)
        with self.assertRaises(Exception) as cm:
            auth_mod.check_login_allowed(k)
        msg = str(getattr(cm.exception, "detail", cm.exception))
        self.assertTrue("频繁" in msg or "429" in str(getattr(cm.exception, "status_code", "")))
        auth_mod.note_login_success(k)
        auth_mod.check_login_allowed(k)

    def test_recovery_returns_code(self) -> None:
        from app import auth as auth_mod

        code = auth_mod.create_account("admin", "secret123")
        new_code = auth_mod.reset_with_recovery(code, "admin", "secret456")
        self.assertTrue(new_code and new_code != code)

    def test_cookie_secure_flag(self) -> None:
        from starlette.responses import Response

        from app import auth as auth_mod

        r = Response()
        auth_mod.set_session_cookie(r, "tok")
        cookies = r.headers.getlist("set-cookie")
        self.assertTrue(any("Secure" in c for c in cookies))
        self.assertTrue(any("HttpOnly" in c for c in cookies))

    def test_import_and_fts_search(self) -> None:
        from sqlalchemy import select, text

        from app.database import SessionLocal, fts_available
        from app.importer import import_all
        from app.models import Book

        novels = self._tmp / "novels" / "玄幻"
        novels.mkdir(parents=True)
        (novels / "甲书.txt").write_text("第一章 开始\n内容甲", encoding="utf-8")
        (novels / "乙书.txt").write_text("第一章 开始\n内容乙", encoding="utf-8")
        res = import_all()
        self.assertGreaterEqual(len(res.added), 2, res.summary)

        s = SessionLocal()
        books = s.execute(select(Book)).scalars().all()
        self.assertGreaterEqual(len(books), 2)
        if fts_available():
            rows = s.execute(
                text("SELECT rowid FROM books_fts WHERE books_fts MATCH :q"), {"q": "甲书"}
            ).all()
            self.assertTrue(rows)
        s.close()

    def test_content_pack_offsets(self) -> None:
        """正文出库：导入后 content 为空，正文包偏移可读回原文。"""
        from sqlalchemy import select

        from app.content_store import content_pack_path, read_chapter_text
        from app.database import SessionLocal
        from app.importer import import_all
        from app.models import Chapter

        novels = self._tmp / "novels" / "玄幻"
        novels.mkdir(parents=True)
        body = "第一章 开始\n正文甲内容\n\n第二章 继续\n正文乙内容"
        (novels / "偏移书.txt").write_text(body, encoding="utf-8")
        self.assertTrue(import_all().added)

        s = SessionLocal()
        chs = s.execute(select(Chapter).order_by(Chapter.index)).scalars().all()
        s.close()
        self.assertGreaterEqual(len(chs), 1)
        for ch in chs:
            self.assertEqual(ch.content, "")
            self.assertGreater(ch.content_chars, 0)
            self.assertGreater(ch.content_length, 0)
        joined = "".join(
            read_chapter_text(ch.book_id, ch.content_offset, ch.content_length, ch.content)
            for ch in chs
        )
        self.assertIn("正文甲内容", joined)
        self.assertIn("正文乙内容", joined)
        self.assertTrue(content_pack_path(chs[0].book_id).is_file())

    def test_toc_does_not_load_content(self) -> None:
        """目录接口只投影标题列。"""
        from sqlalchemy import select

        from app.database import SessionLocal
        from app.importer import import_all
        from app.models import Book
        from app.routers import public as public_mod

        novels = self._tmp / "novels" / "玄幻"
        novels.mkdir(parents=True)
        (novels / "目录书.txt").write_text("第一章 A\n甲\n第二章 B\n乙", encoding="utf-8")
        import_all()

        s = SessionLocal()
        book = s.execute(select(Book)).scalars().first()
        self.assertIsNotNone(book)

        class Req:
            headers = {}

        r = public_mod.list_chapters(Req(), book_id=book.id, page=1, page_size=50, db=s)
        self.assertGreaterEqual(r["total"], 1)
        self.assertTrue(r["items"][0]["name"])
        # 投影结果不应包含正文字段
        self.assertNotIn("content", r["items"][0])
        s.close()

    def test_import_status_progress_fields(self) -> None:
        """导入完成后状态带进度字段，可供进度条/日志使用。"""
        from app.importer import get_import_status, import_all

        novels = self._tmp / "novels" / "玄幻"
        novels.mkdir(parents=True)
        (novels / "进度书.txt").write_text("第一章 开始\n内容", encoding="utf-8")
        res = import_all()
        self.assertGreaterEqual(len(res.added), 1)
        st = get_import_status()
        # 同步 import_all 也会写进度字段
        self.assertIn("percent", st)
        self.assertIn("total", st)
        self.assertIn("done", st)
        self.assertIn("added_n", st)
        self.assertGreaterEqual(st.get("added_n", 0), 1)
        self.assertEqual(st.get("total", 0), st.get("done", 0))

    def test_import_cancel_flag(self) -> None:
        from app.importer import get_import_status, request_import_cancel

        st = get_import_status()
        self.assertIn("cancel_requested", st)
        self.assertFalse(request_import_cancel())

    def test_ensure_category_tag_public(self) -> None:
        from app.importer import ensure_category_tag

        self.assertTrue(ensure_category_tag("热血", "未分类").startswith("未分类"))
        self.assertNotIn("未分类", ensure_category_tag("未分类,热血", "玄幻"))

    def test_two_level_category_map(self) -> None:
        from app.config import category_tree, make_category_label, map_site_category

        self.assertEqual(map_site_category("", "玄幻"), ("", "玄幻"))
        self.assertEqual(map_site_category("起点", "玄幻奇幻"), ("起点", "玄幻"))
        self.assertEqual(map_site_category("qidian", "武侠仙侠"), ("起点", "仙侠"))
        self.assertEqual(map_site_category("番茄", "西方奇幻"), ("番茄", "西方奇幻"))
        self.assertEqual(map_site_category("fanqie", "衍生"), ("番茄", "男频衍生"))
        self.assertEqual(make_category_label(*map_site_category("起点", "历史")), "起点-历史")
        self.assertEqual([x["key"] for x in category_tree()], ["", "起点", "番茄", "纵横"])

    def test_source_category_filter(self) -> None:
        """书源+分类筛选：起点-都市 应能被 source=起点 & category=都市 命中。"""
        from app.database import SessionLocal, get_db
        from app.models import Book
        from app.routers.admin import admin_list_books

        s = SessionLocal()
        s.add_all(
            [
                Book(title="甲", author="A", category="起点-都市", source="起点", word_count=1, chapter_count=1),
                Book(title="乙", author="B", category="番茄-都市日常", source="番茄", word_count=1, chapter_count=1),
                Book(title="丙", author="C", category="都市", source="", word_count=1, chapter_count=1),
            ]
        )
        s.commit()
        s.close()

        class Req:
            headers = {}

        db = next(get_db())
        r = admin_list_books(
            Req(),
            q=None,
            category="都市",
            source="起点",
            status=None,
            tag=None,
            sort="updated",
            page=1,
            page_size=20,
            db=db,
        )
        names = [i["name"] for i in r["items"]]
        self.assertEqual(names, ["甲"])
        r2 = admin_list_books(
            Req(),
            q=None,
            category="都市",
            source=None,
            status=None,
            tag=None,
            sort="updated",
            page=1,
            page_size=20,
            db=db,
        )
        self.assertEqual(set(i["name"] for i in r2["items"]), {"甲", "丙"})
        db.close()

    def test_scrape_mode_normalize(self) -> None:
        """刮削方式归一：browser/fnos → chrome，未知 → auto。"""
        from app.scrapers.mode import normalize_mode

        self.assertEqual(normalize_mode("api"), "api")
        self.assertEqual(normalize_mode("chrome"), "chrome")
        self.assertEqual(normalize_mode("browser"), "chrome")
        self.assertEqual(normalize_mode("fnos-chrome"), "chrome")
        self.assertEqual(normalize_mode("nope"), "auto")
        self.assertEqual(normalize_mode(None), "auto")

    def test_book_list_item_title_alias(self) -> None:
        """列表项 name 与 title 同值，契约统一。"""
        from app.models import Book
        from app.serializers import book_list_item

        b = Book(id=1, title="测试书", author="作者", category="都市", tags="", intro="")
        data = book_list_item(b)
        self.assertEqual(data["name"], "测试书")
        self.assertEqual(data["title"], "测试书")


if __name__ == "__main__":
    unittest.main()
