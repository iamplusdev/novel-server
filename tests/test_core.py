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
        from app.auth import reset_auth_cache

        # 每个用例使用独立临时目录，清空凭据缓存避免串数据
        reset_auth_cache()

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

    def test_cover_thumb_generation(self) -> None:
        """Pillow 可用时按需生成 webp 缩略图，宽度受限且可复用缓存。"""
        from app import thumbs

        if thumbs.Image is None or thumbs.ImageOps is None:
            self.skipTest("未安装 Pillow")

        from PIL import Image as PILImage

        covers = self.cfg.settings.covers_dir
        name = "1_generated.jpg"
        PILImage.new("RGB", (600, 900), (200, 30, 30)).save(covers / name, format="JPEG")

        out = thumbs.ensure_thumb(name, 200)
        self.assertIsNotNone(out)
        self.assertTrue(out.is_file())
        with PILImage.open(out) as im:
            self.assertEqual(im.format, "WEBP")
            self.assertLessEqual(im.width, 200)
        # 再次调用命中缓存，路径一致
        self.assertEqual(thumbs.ensure_thumb(name, 200), out)

    def test_rebuild_thumbs_idempotent(self) -> None:
        """批量回填：首次生成、二次跳过、force 重建、无封面跳过。"""
        from app import thumbs
        from app.models import Book

        if thumbs.Image is None or thumbs.ImageOps is None:
            self.skipTest("未安装 Pillow")
        from PIL import Image as PILImage

        name = "1_rebuild.jpg"
        PILImage.new("RGB", (600, 900), (20, 120, 200)).save(
            self.cfg.settings.covers_dir / name, format="JPEG"
        )
        book = Book(title="回填书", cover_file=name)

        first = thumbs.rebuild_thumbs([book])
        self.assertTrue(first["available"])
        self.assertEqual(first["generated"], 1)
        self.assertEqual(first["skipped"], 0)

        second = thumbs.rebuild_thumbs([book])
        self.assertEqual(second["generated"], 0)
        self.assertEqual(second["skipped"], 1)

        forced = thumbs.rebuild_thumbs([book], force=True)
        self.assertEqual(forced["generated"], 1)

        no_cover = thumbs.rebuild_thumbs([Book(title="无封面", cover_file="")])
        self.assertEqual(no_cover["skipped"], 1)

    def test_rebuild_thumbs_without_pillow(self) -> None:
        """未安装 Pillow 时返回 available=false，不抛异常。"""
        from unittest import mock

        from app import thumbs
        from app.models import Book

        with mock.patch.object(thumbs, "Image", None), mock.patch.object(
            thumbs, "ImageOps", None
        ):
            res = thumbs.rebuild_thumbs([Book(title="无 Pillow", cover_file="x.jpg")])
        self.assertFalse(res["available"])
        self.assertEqual(res["generated"], 0)

    def test_rebuild_thumbs_endpoint(self) -> None:
        """管理端接口只处理有封面的书，并返回统计。"""
        from app import thumbs
        from app.database import SessionLocal, get_db
        from app.models import Book
        from app.routers.admin import ThumbsRebuildIn, admin_rebuild_thumbs

        if thumbs.Image is None or thumbs.ImageOps is None:
            self.skipTest("未安装 Pillow")
        from PIL import Image as PILImage

        name = "1_endpoint.jpg"
        PILImage.new("RGB", (400, 600), (10, 160, 90)).save(
            self.cfg.settings.covers_dir / name, format="JPEG"
        )
        s = SessionLocal()
        s.add_all(
            [
                Book(title="有封面", cover_file=name),
                Book(title="无封面", cover_file=""),
            ]
        )
        s.commit()
        s.close()

        db = next(get_db())
        try:
            res = admin_rebuild_thumbs(ThumbsRebuildIn(limit=10), db=db)
        finally:
            db.close()
        self.assertTrue(res["ok"])
        self.assertTrue(res["available"])
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["generated"], 1)

    def test_cover_thumb_rejects_unsafe_names(self) -> None:
        """路径穿越/非图片扩展名一律拒绝。"""
        from app import thumbs

        for bad in ("../evil.jpg", "a/b.jpg", "..\\x.jpg", ".hidden.jpg", "x.txt", ""):
            self.assertIsNone(thumbs.safe_cover_path(bad))
            self.assertIsNone(thumbs.ensure_thumb(bad))

    def test_cover_thumb_falls_back_without_pillow(self) -> None:
        """未安装 Pillow 时接口返回原图，不报错。"""
        from unittest import mock

        from app import main as main_mod
        from app import thumbs

        name = "2_nopillow.jpg"
        (self.cfg.settings.covers_dir / name).write_bytes(b"\xff\xd8\xff\xe0not-a-real-jpeg")
        with mock.patch.object(thumbs, "Image", None), mock.patch.object(thumbs, "ImageOps", None):
            self.assertIsNone(thumbs.ensure_thumb(name, 320))
            resp = main_mod.cover_thumb(name, 320)
        self.assertEqual(Path(resp.path).name, name)
        # 回退原图不长久缓存，安装 Pillow/回填后能及时切换到缩略图
        self.assertEqual(resp.headers.get("cache-control"), "no-cache")

    def test_safe_delete_cover_removes_thumbs(self) -> None:
        """删除/更换封面时同步清理派生缩略图。"""
        from app.config import safe_delete_cover

        covers = self.cfg.settings.covers_dir
        name = "3_del.jpg"
        (covers / name).write_bytes(b"\xff\xd8\xff")
        tdir = covers / "thumbs"
        tdir.mkdir(exist_ok=True)
        thumb = tdir / "3_del_320.webp"
        thumb.write_bytes(b"x")

        self.assertTrue(safe_delete_cover(name))
        self.assertFalse(thumb.exists())

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

    def test_auth_cache_avoids_disk_read(self) -> None:
        """凭据缓存命中后不再读文件（每请求只 stat 一次）。"""
        from unittest import mock

        from app import auth as auth_mod

        auth_mod.reset_auth_cache()
        auth_mod.create_account("cacheuser", "secret123")
        auth_mod.reset_auth_cache()

        real_read = Path.read_text
        calls = {"n": 0}

        def _counting(path_self, *args, **kwargs):
            calls["n"] += 1
            return real_read(path_self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", _counting):
            self.assertIsNotNone(auth_mod.load_auth())
            self.assertIsNotNone(auth_mod.load_auth())
        self.assertEqual(calls["n"], 1)

    def test_auth_cache_invalidates_on_external_change(self) -> None:
        """外部修改 auth.json 后缓存立即失效，旧 token 不再通过。"""
        import json as _json
        import time as _time

        from app import auth as auth_mod

        auth_mod.reset_auth_cache()
        auth_mod.create_account("cacheuser", "secret123")
        token = auth_mod.login("cacheuser", "secret123")["token"]
        self.assertEqual(auth_mod.verify_token(token), "cacheuser")

        path = auth_mod.auth_path()
        data = _json.loads(path.read_text(encoding="utf-8"))
        data["secret"] = "0" * 64
        path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # 部分文件系统 mtime 精度较低，显式推进时间戳保证缓存签名变化
        future = _time.time() + 2
        os.utime(path, (future, future))

        with self.assertRaises(Exception):
            auth_mod.verify_token(token)

    def test_save_auth_atomic(self) -> None:
        """写入失败时原 auth.json 不变，且不残留临时文件。"""
        from unittest import mock

        from app import auth as auth_mod

        auth_mod.reset_auth_cache()
        auth_mod.create_account("atomic", "secret123")
        path = auth_mod.auth_path()
        before = path.read_bytes()

        data = auth_mod.load_auth()
        self.assertIsNotNone(data)
        data["password_hash"] = "changed"
        with mock.patch.object(auth_mod.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                auth_mod.save_auth(data)

        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_import_and_fts_search(self) -> None:
        """中文子串搜索必须命中（≥3 字走 FTS，2 字由 LIKE 兜底）。"""
        from sqlalchemy import select, text

        from app.book_query import apply_search
        from app.database import SessionLocal, fts_available
        from app.importer import import_all
        from app.models import Book

        novels = self._tmp / "novels" / "起点" / "玄幻"
        novels.mkdir(parents=True)
        (novels / "斗破苍穹.txt").write_text("第一章 开始\n内容甲", encoding="utf-8")
        (novels / "凡人修仙传.txt").write_text("第一章 开始\n内容乙", encoding="utf-8")
        res = import_all()
        self.assertGreaterEqual(len(res.added), 2, res.summary)

        s = SessionLocal()
        try:
            titles = [b.title for b in s.execute(select(Book)).scalars().all()]
            self.assertGreaterEqual(len(titles), 2)
            if fts_available():
                rows = s.execute(
                    text("SELECT rowid FROM books_fts WHERE books_fts MATCH :q"),
                    {"q": '"斗破苍"'},
                ).all()
                self.assertTrue(rows)
            # 端到端：3 字走 FTS、2 字走 LIKE，均应返回同一本书
            for q in ("斗破苍", "斗破"):
                hits = [
                    b.title
                    for b in s.execute(apply_search(select(Book), s, q)).scalars().all()
                ]
                self.assertIn("斗破苍穹", hits, q)
        finally:
            s.close()

    def test_fts_migrates_unicode61_to_trigram(self) -> None:
        """旧库的 unicode61 索引在 init_db 时自动迁移为 trigram。"""
        from sqlalchemy import text

        from app import database as dbmod

        if dbmod._trigram_supported is False:
            self.skipTest("当前 SQLite 不支持 trigram")

        # 模拟旧库：手工建 unicode61 索引
        with dbmod.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS books_fts"))
            conn.execute(
                text(
                    "CREATE VIRTUAL TABLE books_fts USING fts5("
                    "title, author, tags, intro, content='books', "
                    "content_rowid='id', tokenize='unicode61')"
                )
            )
        dbmod.init_db()

        with dbmod.engine.connect() as conn:
            sql = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='books_fts'")
            ).scalar()
        self.assertIn("trigram", (sql or "").lower())

    def test_sort_indexes_created(self) -> None:
        """列表排序字段在初始化时补齐索引（旧库也能补）。"""
        from sqlalchemy import text

        from app import database as dbmod

        dbmod.init_db()
        with dbmod.engine.connect() as conn:
            names = {
                r[0]
                for r in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='books'")
                ).all()
            }
        for name in ("ix_books_updated_at", "ix_books_word_count", "ix_books_chapter_count"):
            self.assertIn(name, names)

    def test_index_html_no_cache(self) -> None:
        """SPA 入口 index.html 必须 no-cache，避免升级后仍加载旧入口。"""
        from unittest import mock

        from app import main as main_mod

        dist = self._tmp / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html></html>", encoding="utf-8")
        with mock.patch.object(main_mod, "DIST_DIR", dist):
            resp = main_mod.spa_fallback("")
        self.assertEqual(resp.headers.get("cache-control"), "no-cache")

    def test_content_pack_offsets(self) -> None:
        """正文出库：导入后 content 为空，正文包偏移可读回原文。"""
        from sqlalchemy import select

        from app.content_store import content_pack_path, read_chapter_text
        from app.database import SessionLocal
        from app.importer import import_all
        from app.models import Chapter

        novels = self._tmp / "novels" / "起点" / "玄幻"
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

    def test_import_utf16_bom(self) -> None:
        """UTF-16(带 BOM) 文本也能导入（曾因编解码器 BOM 检查抛 UnicodeError 失败）。"""
        from sqlalchemy import select

        from app.content_store import read_chapter_text
        from app.database import SessionLocal
        from app.importer import import_all
        from app.models import Book, Chapter

        novels = self._tmp / "novels" / "未分类"
        novels.mkdir(parents=True)
        body = "我在精神病院学斩神\n第一章 开始\n正文甲内容\n第二章 继续\n正文乙内容"
        (novels / "斩神.txt").write_bytes(body.encode("utf-16"))

        res = import_all()
        self.assertTrue(res.added, res.summary)

        s = SessionLocal()
        book = s.execute(select(Book).where(Book.title == "斩神")).scalars().first()
        self.assertIsNotNone(book)
        chs = (
            s.execute(
                select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.index)
            )
            .scalars()
            .all()
        )
        joined = "".join(
            read_chapter_text(c.book_id, c.content_offset, c.content_length, c.content)
            for c in chs
        )
        self.assertIn("正文甲内容", joined)
        self.assertIn("正文乙内容", joined)
        s.close()

    def test_import_only_paths_and_failed_items(self) -> None:
        """失败项带相对路径；only_paths 只重试指定文件。"""
        from unittest import mock

        from app import importer

        novels = self.cfg.settings.novels_dir / "未分类"
        novels.mkdir(parents=True, exist_ok=True)
        good = novels / "good.txt"
        bad = novels / "bad.txt"
        body = "第一章 开始\n正文内容"
        good.write_text(body, encoding="utf-8")
        bad.write_text(body, encoding="utf-8")

        real_loader = importer.load_txt_book_with_hash

        def fake_loader(path, category, cancel=None):
            if Path(path).name == "bad.txt":
                raise ValueError("坏文件")
            return real_loader(path, category, cancel=cancel)

        with mock.patch.object(importer, "load_txt_book_with_hash", side_effect=fake_loader):
            res = importer.import_all(
                only_paths={str(good.resolve()), str(bad.resolve())}
            )

        self.assertEqual(len(res.added), 1, res.summary)
        self.assertEqual(len(res.failed_items), 1)
        item = res.failed_items[0]
        self.assertEqual(item["name"], "bad.txt")
        self.assertEqual(item["path"], "未分类/bad.txt")
        self.assertIn("坏文件", item["error"])
        self.assertEqual(res.to_dict()["failed_items"], res.failed_items)

    def test_import_retry_path_validation(self) -> None:
        """重试路径必须位于 NOVELS_DIR 内且为存在的 TXT。"""
        from fastapi import HTTPException

        from app.routers.admin import _validated_retry_paths

        novels = self.cfg.settings.novels_dir / "未分类"
        novels.mkdir(parents=True, exist_ok=True)
        ok = novels / "ok.txt"
        ok.write_text("第一章 开始\n正文", encoding="utf-8")

        self.assertEqual(
            _validated_retry_paths(["未分类/ok.txt", "未分类/ok.txt"]),
            [str(ok.resolve())],
        )
        with self.assertRaises(HTTPException):
            _validated_retry_paths(["../outside.txt"])
        with self.assertRaises(HTTPException):
            _validated_retry_paths(["未分类/ok.md"])

    def test_import_log_keeps_failed_items(self) -> None:
        """失败项随历史日志落库，刷新页面后仍可重试。"""
        from app.importer import ImportResult, query_import_logs, save_import_log

        item = {"path": "未分类/bad.txt", "name": "bad.txt", "error": "解析失败"}
        result = ImportResult(failed=["bad.txt: 解析失败"], failed_items=[item], skipped=["ok"])
        save_import_log(result, started_at="2026-01-01T00:00:00", mode="local")

        logs = query_import_logs(limit=1)
        self.assertEqual(logs[0]["detail"]["failed_items"], [item])

    def test_repair_preview_is_read_only(self) -> None:
        """预览只计算动作，不改 DB/正文；随后修复仍按同一计划执行。"""
        from app.database import SessionLocal, get_db
        from app.library_check import preview_repair_book, repair_book
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(
            title="预览书",
            author="A",
            category="未分类",
            word_count=10,
            chapter_count=1,
            updated_at="2026-01-01T00:00:00",
        )
        s.add(book)
        s.flush()
        chapter = Chapter(
            book_id=book.id,
            index=0,
            title="第一章",
            content="正常\x00文本",
            content_chars=7,
            content_offset=0,
            content_length=0,
        )
        s.add(chapter)
        s.commit()
        book_id = book.id
        s.close()

        db = next(get_db())
        try:
            preview = preview_repair_book(db, book_id, mode="auto")
            self.assertTrue(preview["will_change"])
            self.assertIn("清理控制字符/零宽字符", preview["actions"])

            # 预览后数据和更新时间保持不变
            db.expire_all()
            current = db.get(Book, book_id)
            self.assertEqual(current.updated_at, "2026-01-01T00:00:00")

            repaired = repair_book(db, book_id, mode="auto")
            self.assertIn("已清理控制字符/零宽字符", repaired["actions"])
        finally:
            db.close()

    def test_chapter_parse_variants(self) -> None:
        """分章：标题+正文同行 / 全角与大写数字 / 无换行连排 均应识别。"""
        from app.parsers import parse_txt_text

        # 标题与正文同行：标题截到句末标点前，正文并入该章
        chs = parse_txt_text("第一章 重生。夜色沉沉。\n第二章 归来。三年之后。")
        self.assertEqual(len(chs), 2)
        self.assertIn("夜色沉沉", chs[0].content)

        # 全角数字 / 大写数字
        chs = parse_txt_text("第１２３章 A\n内容\n第壹章 B\n内容二")
        self.assertEqual(len(chs), 2)

        # 正文句不应被当成章节标题 → 整本单章
        chs = parse_txt_text("第一章的内容他早忘了。\n第二天他去了城里。")
        self.assertEqual(len(chs), 1)

        # 无换行整行连排（>2000 字）：按章标记虚拟切行
        big = "".join(f"第{i}章 标题。正文。" for i in range(1, 401))
        chs = parse_txt_text(big)
        self.assertGreaterEqual(len(chs), 300)

    def test_encoding_detection_no_bom_utf16(self) -> None:
        """无 BOM 的单字节文本不得被判为 utf-16（否则整篇乱码、无法分章）。"""
        from app.parsers import decode_bytes, detect_encoding

        raw = ("第一章 开始\n正文内容。\n" * 300).encode("utf-8")
        self.assertEqual(detect_encoding(raw[:4096]), "utf-8")
        # 采样 head+mid 拼接截断多字节字符时，仍应选 utf-8
        self.assertEqual(detect_encoding(raw[:100] + raw[3:103]), "utf-8")
        self.assertIn("第一章", decode_bytes(raw))

    def test_scraper_settings_roundtrip(self) -> None:
        """刮削参数：默认值、保存、范围夹紧、长休息区间颠倒自动交换。"""
        from app import scraper_settings as ss

        ss.reset_cache()
        self.assertEqual(ss.get_all()["long_pause_every"], 5)
        ss.update({"delay": 3.5})
        self.assertEqual(ss.get("delay"), 3.5)
        ss.update({"retry_max": 999})
        self.assertLessEqual(ss.get("retry_max"), 20)
        u = ss.update({"long_pause_min": 20, "long_pause_max": 5})
        self.assertLessEqual(u["long_pause_min"], u["long_pause_max"])
        ss.reset_cache()

    def test_toc_does_not_load_content(self) -> None:
        """目录接口只投影标题列。"""
        from sqlalchemy import select

        from app.database import SessionLocal
        from app.importer import import_all
        from app.models import Book
        from app.routers import public as public_mod

        novels = self._tmp / "novels" / "未分类"
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

        novels = self._tmp / "novels" / "未分类"
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

    def test_import_only_source_and_uncategorized(self) -> None:
        """只扫书源+未分类：根目录散落 txt、其他目录、旧一级分类均跳过。"""
        from app.importer import import_all

        root = self._tmp / "novels"
        (root / "起点" / "都市").mkdir(parents=True)
        (root / "未分类").mkdir(parents=True)
        (root / "玄幻").mkdir(parents=True)  # 旧一级分类，应跳过
        (root / "备份").mkdir(parents=True)  # 其他目录，应跳过
        (root / "起点" / "都市" / "源书.txt").write_text("第一章 A\n甲", encoding="utf-8")
        (root / "未分类" / "散书.txt").write_text("第一章 B\n乙", encoding="utf-8")
        (root / "根目录书.txt").write_text("第一章 C\n丙", encoding="utf-8")
        (root / "玄幻" / "旧书.txt").write_text("第一章 D\n丁", encoding="utf-8")
        (root / "备份" / "备书.txt").write_text("第一章 E\n戊", encoding="utf-8")

        res = import_all()
        self.assertEqual(len(res.added), 2, res.summary)
        labels = " ".join(res.added)
        self.assertIn("源书", labels)
        self.assertIn("散书", labels)
        self.assertNotIn("根目录书", labels)
        self.assertNotIn("旧书", labels)
        self.assertNotIn("备书", labels)

    def test_ensure_category_tag_public(self) -> None:
        from app.importer import ensure_category_tag

        self.assertTrue(ensure_category_tag("热血", "未分类").startswith("未分类"))
        self.assertNotIn("未分类", ensure_category_tag("未分类,热血", "玄幻"))

    def test_two_level_category_map(self) -> None:
        from app.config import (
            QIDIAN_CATEGORIES,
            category_tree,
            make_category_label,
            map_site_category,
            to_qidian_category,
        )

        # 本地/起点：别名归到起点 15 类
        self.assertEqual(map_site_category("", "玄幻"), ("", "玄幻"))
        self.assertEqual(map_site_category("起点", "玄幻奇幻"), ("起点", "玄幻"))
        self.assertEqual(map_site_category("qidian", "武侠仙侠"), ("起点", "仙侠"))
        # 番茄/纵横原栏目 → 起点标准分类（书源前缀保留）
        self.assertEqual(map_site_category("番茄", "西方奇幻"), ("番茄", "奇幻"))
        self.assertEqual(map_site_category("fanqie", "衍生"), ("番茄", "诸天无限"))
        self.assertEqual(map_site_category("番茄", "都市高武"), ("番茄", "都市"))
        self.assertEqual(map_site_category("纵横", "玄幻奇幻"), ("纵横", "玄幻"))
        self.assertEqual(map_site_category("纵横", "武侠仙侠"), ("纵横", "仙侠"))
        self.assertEqual(map_site_category("纵横", "奇闻异事"), ("纵横", "悬疑灵异"))
        self.assertEqual(map_site_category("纵横", "N次元"), ("纵横", "轻小说"))
        # 风格标签只进 tags，不作分类
        self.assertEqual(map_site_category("番茄", "第一人称"), ("番茄", "未分类"))
        self.assertEqual(map_site_category("番茄", "开局"), ("番茄", "未分类"))
        self.assertEqual(to_qidian_category("搞笑轻松"), "")
        self.assertEqual(make_category_label(*map_site_category("起点", "历史")), "起点-历史")
        self.assertEqual([x["key"] for x in category_tree()], ["", "起点", "番茄", "纵横"])
        # 三家分类选项统一为起点 15 类
        for node in category_tree():
            if node["key"]:
                self.assertEqual(node["categories"], list(QIDIAN_CATEGORIES))

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

    def test_book_content_search(self) -> None:
        """书内搜索：跨章命中、上下文片段、大小写不敏感、limit 与 total 区分。"""
        from app.database import SessionLocal, get_db
        from app.models import Book, Chapter
        from app.routers.admin import admin_search_book

        s = SessionLocal()
        b = Book(title="搜索书", author="A", category="都市", word_count=10, chapter_count=3)
        s.add(b)
        s.flush()
        s.add_all(
            [
                Chapter(book_id=b.id, index=0, title="第一章", content="开篇普通内容，主角名叫林凡。"),
                Chapter(book_id=b.id, index=1, title="第二章", content="林凡再次出现，林凡很强。"),
                Chapter(book_id=b.id, index=2, title="第三章", content="Alpha 测试内容"),
            ]
        )
        s.commit()
        bid = b.id
        s.close()

        db = next(get_db())
        try:
            r = admin_search_book(bid, q="林凡", limit=10, db=db)
            self.assertEqual(r["total"], 3)
            self.assertEqual(len(r["items"]), 3)
            self.assertIn("林凡", r["items"][0]["snippet"])
            self.assertGreaterEqual(r["items"][0]["offset"], 0)
            # 命中来自不同章节
            self.assertNotEqual(r["items"][0]["chapter_id"], r["items"][2]["chapter_id"])
            # 大小写不敏感
            self.assertEqual(admin_search_book(bid, q="alpha", limit=10, db=db)["total"], 1)
            # limit 只截断返回条数，total 仍为全书命中数
            capped = admin_search_book(bid, q="林凡", limit=1, db=db)
            self.assertEqual(capped["total"], 3)
            self.assertEqual(len(capped["items"]), 1)
            # 无命中
            self.assertEqual(admin_search_book(bid, q="不存在", limit=10, db=db)["items"], [])
        finally:
            db.close()

    def test_batch_update_books(self) -> None:
        """批量编辑：分类同步书源、标签追加/移除/替换、状态更新。"""
        from sqlalchemy import select

        from app.database import SessionLocal, get_db
        from app.models import Book
        from app.routers.admin import BatchUpdateIn, admin_batch_update

        s = SessionLocal()
        b1 = Book(title="甲", author="A", category="未分类", tags="未分类,热血", status="未知")
        b2 = Book(title="乙", author="B", category="都市", tags="都市", status="连载")
        s.add_all([b1, b2])
        s.commit()
        ids = [b1.id, b2.id]
        s.close()

        db = next(get_db())
        try:
            # 分类 + 标签追加 + 状态
            r = admin_batch_update(
                BatchUpdateIn(
                    ids=ids,
                    category_source="起点",
                    category_name="玄幻",
                    tags="热血,玄幻",
                    tags_mode="append",
                    status="完结",
                ),
                db=db,
            )
            self.assertEqual(r["updated_count"], 2)
            books = db.execute(select(Book).where(Book.id.in_(ids))).scalars().all()
            for b in books:
                self.assertEqual(b.category, "起点-玄幻")
                self.assertEqual(b.source, "起点")
                self.assertEqual(b.status, "完结")
                tags = b.tags.split(",")
                self.assertIn("热血", tags)
                self.assertIn("玄幻", tags)
                self.assertNotIn("未分类", tags)

            # 移除标签
            admin_batch_update(
                BatchUpdateIn(ids=ids, tags="热血", tags_mode="remove"), db=db
            )
            books = db.execute(select(Book).where(Book.id.in_(ids))).scalars().all()
            for b in books:
                self.assertNotIn("热血", b.tags.split(","))

            # 替换为空串 → 清空标签
            admin_batch_update(BatchUpdateIn(ids=ids, tags="", tags_mode="replace"), db=db)
            books = db.execute(select(Book).where(Book.id.in_(ids))).scalars().all()
            for b in books:
                self.assertEqual(b.tags, "")

            # 本地分类：清空书源
            admin_batch_update(
                BatchUpdateIn(ids=[ids[0]], category_source="", category_name="都市"), db=db
            )
            b = db.get(Book, ids[0])
            self.assertEqual(b.category, "都市")
            self.assertEqual(b.source, "")
        finally:
            db.close()

    def test_batch_scrape_result_report(self) -> None:
        """批量刮削结果：同书号 upsert，兜底恢复覆盖失败记录。"""
        from app import batch_scrape as bs

        with bs._results_lock:
            bs._status["results"] = []
        try:
            bs._record_result(
                book_id=1, title="甲", action="failed", message="详情失败", source="起点"
            )
            bs._record_result(
                book_id=1,
                title="甲",
                action="recovered",
                message="浏览器兜底恢复",
                source="起点",
                hit_title="甲站",
                score=0.91,
                recovered=True,
            )
            bs._record_result(
                book_id=2, title="乙", action="skipped", message="未达到匹配阈值"
            )

            status = bs.get_batch_status()
            self.assertEqual(len(status["results"]), 2)
            first = status["results"][0]
            self.assertEqual(first["action"], "recovered")
            self.assertTrue(first["recovered"])
            self.assertEqual(first["hit_title"], "甲站")
            self.assertEqual(first["score"], 0.91)
            self.assertEqual(status["results"][1]["action"], "skipped")

            # 返回的是副本，调用方修改不会污染全局状态
            status["results"][0]["title"] = "changed"
            self.assertEqual(bs.get_batch_status()["results"][0]["title"], "甲")
        finally:
            with bs._results_lock:
                bs._status["results"] = []

    def test_sort_books_by_read_at(self) -> None:
        """read=true + sort=read：只返回读过的书，按最近阅读倒序。"""
        from app.database import SessionLocal, get_db
        from app.models import Book
        from app.routers.admin import admin_list_books

        s = SessionLocal()
        s.add_all(
            [
                Book(
                    title="旧读", author="A", category="都市", read_at="2026-01-01T10:00:00",
                    read_percent=20, word_count=1, chapter_count=1,
                ),
                Book(
                    title="新读", author="B", category="都市", read_at="2026-02-01T10:00:00",
                    read_percent=50, word_count=1, chapter_count=1,
                ),
                Book(title="未读", author="C", category="都市", read_at="", word_count=1, chapter_count=1),
            ]
        )
        s.commit()
        s.close()

        class Req:
            headers = {}

        db = next(get_db())
        try:
            r = admin_list_books(
                Req(),
                q=None,
                category=None,
                source=None,
                status=None,
                tag=None,
                scraped=None,
                read=True,
                sort="read",
                page=1,
                page_size=20,
                db=db,
            )
            self.assertEqual([i["name"] for i in r["items"]], ["新读", "旧读"])
            self.assertTrue(r["items"][0]["read_at"].startswith("2026-02-01"))
        finally:
            db.close()

    def test_progress_filename_matches_legado(self) -> None:
        """文件名与 Legado 的 normalizeFileName + URL 编码保持一致。"""
        from urllib.parse import quote

        from app.sync_progress import progress_filename

        self.assertEqual(
            progress_filename("三体", "刘慈欣"),
            quote("三体_刘慈欣", safe="") + ".json",
        )
        # 非法文件名字符先替换为下划线
        self.assertEqual(
            progress_filename("A:B?C", "D"),
            quote("A_B_C_D", safe="") + ".json",
        )
        self.assertIn("%20", progress_filename("A B", "C"))

    def test_sync_resolve_chapter_title_first(self) -> None:
        """章节匹配标题优先：序号错位时仍能按标题命中。"""
        from app.models import Chapter
        from app.sync_progress import resolve_chapter

        chapters = [
            Chapter(id=1, book_id=1, index=0, title="第一章 开始", content=""),
            Chapter(id=2, book_id=1, index=1, title="第二章 继续", content=""),
        ]
        ch = resolve_chapter(
            chapters,
            {"durChapterIndex": 0, "durChapterTitle": "第二章  继续"},
        )
        self.assertEqual(ch.id, 2)

    def test_sync_pull_latest_wins(self) -> None:
        """远端时间更新时写入本地进度，并返回目标章节。"""
        import json
        import time
        from unittest import mock

        from app import sync_progress
        from app.database import SessionLocal
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(
            title="同步书", author="作者", category="都市",
            read_at="2026-01-01T00:00:00", read_chapter_index=0,
            read_percent=10, word_count=10, chapter_count=2,
        )
        s.add(book)
        s.flush()
        c1 = Chapter(book_id=book.id, index=0, title="第一章", content="a")
        c2 = Chapter(book_id=book.id, index=1, title="第二章", content="b")
        s.add_all([c1, c2])
        s.commit()
        bid, c2id = book.id, c2.id
        s.close()

        remote = {
            "name": "同步书",
            "author": "作者",
            "durChapterIndex": 1,
            "durChapterPos": 120,
            "durChapterTime": int(time.time() * 1000) + 1000,
            "durChapterTitle": "第二章",
        }
        settings = {
            "enabled": True,
            "url": "https://dav.example.com/dav",
            "username": "u",
            "password": "p",
            "dir": "legado",
            "timeout": 6,
            "verify_tls": True,
        }

        class FakeClient:
            def get(self, url):
                return json.dumps(remote).encode()

            def mkcol(self, url):
                pass

            def put(self, url, data, content_type="application/json"):
                pass

        with mock.patch.object(
            sync_progress.webdav_settings, "load", return_value=settings
        ), mock.patch.object(sync_progress, "_client", return_value=FakeClient()):
            db = SessionLocal()
            result = sync_progress.pull_progress(db, bid)
            db.close()

        self.assertTrue(result["updated"])
        self.assertEqual(result["chapter_id"], c2id)
        self.assertEqual(result["chapter_pos"], 120)
        db = SessionLocal()
        saved = db.get(Book, bid)
        self.assertEqual(saved.read_chapter_index, 1)
        self.assertNotEqual(saved.read_at, "2026-01-01T00:00:00")
        db.close()

    def test_sync_pull_keeps_newer_local(self) -> None:
        """远端时间更旧时不覆盖本地进度。"""
        import json
        from unittest import mock

        from app import sync_progress
        from app.database import SessionLocal
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(
            title="本地新", author="作者", category="都市",
            read_at="2099-01-01T00:00:00", read_chapter_index=1,
            read_percent=100, word_count=10, chapter_count=2,
        )
        s.add(book)
        s.flush()
        s.add_all(
            [
                Chapter(book_id=book.id, index=0, title="第一章", content="a"),
                Chapter(book_id=book.id, index=1, title="第二章", content="b"),
            ]
        )
        s.commit()
        bid = book.id
        s.close()

        remote = {
            "name": "本地新", "author": "作者",
            "durChapterIndex": 0, "durChapterPos": 0,
            "durChapterTime": 1000, "durChapterTitle": "第一章",
        }
        settings = {
            "enabled": True, "url": "https://dav.example.com/dav",
            "username": "u", "password": "p", "dir": "legado",
            "timeout": 6, "verify_tls": True,
        }

        class FakeClient:
            def get(self, url):
                return json.dumps(remote).encode()

            def mkcol(self, url):
                pass

            def put(self, url, data, content_type="application/json"):
                pass

        with mock.patch.object(
            sync_progress.webdav_settings, "load", return_value=settings
        ), mock.patch.object(sync_progress, "_client", return_value=FakeClient()):
            db = SessionLocal()
            result = sync_progress.pull_progress(db, bid)
            db.close()

        self.assertFalse(result["updated"])
        db = SessionLocal()
        self.assertEqual(db.get(Book, bid).read_chapter_index, 1)
        db.close()

    def test_sync_push_payload(self) -> None:
        """推送内容符合 Legado BookProgress 字段约定。"""
        import json
        import time
        from unittest import mock

        from app import sync_progress
        from app.database import SessionLocal
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(title="推送书", author="作者", category="都市", word_count=1, chapter_count=1)
        s.add(book)
        s.flush()
        ch = Chapter(book_id=book.id, index=0, title="第一章", content="a")
        s.add(ch)
        s.commit()
        bid, cid = book.id, ch.id
        s.close()

        settings = {
            "enabled": True, "url": "https://dav.example.com/dav",
            "username": "u", "password": "p", "dir": "legado",
            "timeout": 6, "verify_tls": True,
        }
        puts: list[tuple[str, bytes]] = []

        class FakeClient:
            def get(self, url):
                return None

            def mkcol(self, url):
                pass

            def put(self, url, data, content_type="application/json"):
                puts.append((url, data))

        with mock.patch.object(
            sync_progress.webdav_settings, "load", return_value=settings
        ), mock.patch.object(sync_progress, "_client", return_value=FakeClient()):
            now_ms = int(time.time() * 1000)
            db = SessionLocal()
            result = sync_progress.push_progress(db, bid, cid, chapter_pos=42, time_ms=now_ms)
            db.close()

        self.assertTrue(result["pushed"])
        self.assertTrue(puts)
        payload = json.loads(puts[0][1].decode("utf-8"))
        self.assertEqual(payload["name"], "推送书")
        self.assertEqual(payload["author"], "作者")
        self.assertEqual(payload["durChapterIndex"], 0)
        self.assertEqual(payload["durChapterPos"], 42)
        self.assertLessEqual(abs(payload["durChapterTime"] - now_ms), 5000)
        self.assertEqual(payload["durChapterTitle"], "第一章")

    def test_sync_info_diagnostic(self) -> None:
        """详情页诊断：远程文件存在、章节匹配、文件名展示。"""
        import json
        from unittest import mock

        from app import sync_progress
        from app.database import SessionLocal
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(
            title="诊断书", author="作者", category="都市",
            read_at="2026-01-01T00:00:00", read_chapter_index=0,
            word_count=1, chapter_count=2,
        )
        s.add(book)
        s.flush()
        s.add_all(
            [
                Chapter(book_id=book.id, index=0, title="第一章", content="a"),
                Chapter(book_id=book.id, index=1, title="第二章", content="b"),
            ]
        )
        s.commit()
        bid = book.id
        s.close()

        remote = {
            "name": "诊断书", "author": "作者",
            "durChapterIndex": 1, "durChapterPos": 9,
            "durChapterTime": 1700000000000, "durChapterTitle": "第二章",
        }
        settings = {
            "enabled": True, "url": "https://dav.example.com/dav",
            "username": "u", "password": "p", "dir": "legado",
            "timeout": 6, "verify_tls": True,
        }

        class FakeClient:
            def get(self, url):
                return json.dumps(remote).encode()

            def mkcol(self, url):
                pass

            def put(self, url, data, content_type="application/json"):
                pass

        with mock.patch.object(
            sync_progress.webdav_settings, "load", return_value=settings
        ), mock.patch.object(sync_progress, "_client", return_value=FakeClient()):
            db = SessionLocal()
            info = sync_progress.sync_info(db, bid)
            db.close()

        self.assertTrue(info["configured"])
        self.assertTrue(info["remote_exists"])
        self.assertEqual(info["matched"]["index"], 1)
        self.assertEqual(info["filename"], sync_progress.progress_filename("诊断书", "作者"))
        self.assertEqual(info["local"]["read_chapter_index"], 0)

    def test_sync_push_now(self) -> None:
        """详情页手动推送：使用本地 read_chapter_index 组装进度。"""
        import json
        from datetime import datetime
        from unittest import mock

        from app import sync_progress
        from app.database import SessionLocal
        from app.models import Book, Chapter

        s = SessionLocal()
        book = Book(
            title="手动推送", author="作者", category="都市",
            read_chapter_index=1, read_percent=50,
            read_at=datetime.now().isoformat(timespec="seconds"),
            word_count=1, chapter_count=2,
        )
        s.add(book)
        s.flush()
        s.add_all(
            [
                Chapter(book_id=book.id, index=0, title="第一章", content="a"),
                Chapter(book_id=book.id, index=1, title="第二章", content="b"),
            ]
        )
        s.commit()
        bid = book.id
        s.close()

        settings = {
            "enabled": True, "url": "https://dav.example.com/dav",
            "username": "u", "password": "p", "dir": "legado",
            "timeout": 6, "verify_tls": True,
        }
        puts: list[bytes] = []

        class FakeClient:
            def get(self, url):
                return None

            def mkcol(self, url):
                pass

            def put(self, url, data, content_type="application/json"):
                puts.append(data)

        with mock.patch.object(
            sync_progress.webdav_settings, "load", return_value=settings
        ), mock.patch.object(sync_progress, "_client", return_value=FakeClient()):
            result = sync_progress.push_now(bid)

        self.assertTrue(result["pushed"])
        payload = json.loads(puts[0].decode("utf-8"))
        self.assertEqual(payload["durChapterIndex"], 1)
        self.assertEqual(payload["durChapterTitle"], "第二章")

    def test_webdav_client_roundtrip(self) -> None:
        """真实 HTTP 往返：MKCOL/PUT/GET/PROPFIND 与 404 处理。"""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from app.webdav import WebDavClient

        files: dict[str, bytes] = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # 静默测试服务日志
                pass

            def do_MKCOL(self):
                self.send_response(201)
                self.end_headers()

            def do_PUT(self):
                length = int(self.headers.get("Content-Length") or 0)
                files[self.path] = self.rfile.read(length)
                self.send_response(201)
                self.end_headers()

            def do_GET(self):
                data = files.get(self.path)
                if data is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_PROPFIND(self):
                self.send_response(207)
                self.end_headers()

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{srv.server_port}/dav"
            client = WebDavClient(base, "u", "p", timeout=3)
            client.mkcol(f"{base}/legado")
            client.mkcol(f"{base}/legado/bookProgress/")
            target = f"{base}/legado/bookProgress/x.json"
            client.put(target, b'{"a":1}')
            self.assertEqual(client.get(target), b'{"a":1}')
            self.assertIsNone(client.get(f"{base}/legado/bookProgress/none.json"))
            self.assertTrue(client.propfind(base))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_webdav_settings_masks_password(self) -> None:
        """WebDAV 配置：接口不返回密码，空密码不覆盖，可显式清除。"""
        from app import webdav_settings

        webdav_settings.update(
            {
                "enabled": True,
                "url": "https://dav.example.com/dav/",
                "username": "u",
                "password": "secret",
                "dir": "legado",
                "timeout": 6,
                "verify_tls": True,
            }
        )
        pub = webdav_settings.public_dict()
        self.assertNotIn("password", pub)
        self.assertTrue(pub["has_password"])
        self.assertEqual(pub["url"], "https://dav.example.com/dav")

        # 未提供密码时保留原密码
        webdav_settings.update({"url": "https://dav2.example.com/dav"})
        self.assertEqual(webdav_settings.load()["password"], "secret")

        # 显式清除
        webdav_settings.update({"clear_password": True})
        self.assertEqual(webdav_settings.load()["password"], "")

    def test_fanqie_detail_state_parse(self) -> None:
        """番茄详情：creationStatus→连载状态，categoryV2→起点分类；忽略上架态 status。"""
        from app.scrapers.fanqie import (
            _category_from_names,
            _extract_initial_state,
            _names_from_category_v2,
            _status_from_code,
        )

        page = (
            '<script>window.__INITIAL_STATE__={"common":{"id":""},'
            '"page":{"bookName":"测试书","status":1,"category":"",'
            '"categoryV2":"[{\\"Name\\":\\"都市高武\\",\\"MainCategory\\":true},'
            '{\\"Name\\":\\"都市\\",\\"MainCategory\\":false}]",'
            '"creationStatus":0,"wordNumber":12345}}</script>'
        )
        st = _extract_initial_state(page)
        self.assertIsNotNone(st)
        page_st = (st or {}).get("page") or {}
        self.assertEqual(page_st.get("bookName"), "测试书")
        # creationStatus=0 → 完结；不可用 status=1（上架态）误成连载
        self.assertEqual(_status_from_code(page_st.get("creationStatus")), "完结")
        self.assertEqual(_status_from_code(page_st.get("status")), "连载")
        names = _names_from_category_v2(page_st.get("categoryV2"))
        self.assertEqual(names, ["都市高武", "都市"])
        self.assertEqual(_category_from_names(names), "都市")
        self.assertEqual(page_st.get("wordNumber"), 12345)

    def test_fanqie_category_v2_styles(self) -> None:
        """categoryV2 支持 JSON 字符串 / list / 转义 Name。"""
        from app.scrapers.fanqie import _category_from_names, _names_from_category_v2

        self.assertEqual(
            _names_from_category_v2('[{"Name":"西方奇幻","MainCategory":true}]'),
            ["西方奇幻"],
        )
        self.assertEqual(
            _names_from_category_v2([{"Name": "奇闻异事"}, {"Name": "灵异"}]),
            ["奇闻异事", "灵异"],
        )
        # 风格标签不进分类
        self.assertEqual(_category_from_names(["第一人称", "开局"]), "")
        self.assertEqual(_category_from_names(["传统玄幻"]), "玄幻")

    def test_scrape_mode_normalize(self) -> None:
        """刮削方式归一：browser/fnos → chrome，未知 → auto。"""
        from app.scrapers.mode import normalize_mode

        self.assertEqual(normalize_mode("api"), "api")
        self.assertEqual(normalize_mode("chrome"), "chrome")
        self.assertEqual(normalize_mode("browser"), "chrome")
        self.assertEqual(normalize_mode("fnos-chrome"), "chrome")
        self.assertEqual(normalize_mode("nope"), "auto")
        self.assertEqual(normalize_mode(None), "auto")

    def test_chrome_available_cache(self) -> None:
        """chrome_available：探测结果短时缓存，reset 后重新探测。"""
        from unittest import mock

        from app.scrapers import browser_fallback as bf

        bf.reset_chrome_detect_cache()
        with mock.patch.object(bf, "probe_cdp", return_value=True), mock.patch.object(
            bf, "playwright_installed", return_value=True
        ) as m:
            self.assertTrue(bf.chrome_available())
            self.assertTrue(bf.chrome_available())
            # 缓存命中，只探一次
            self.assertEqual(m.call_count, 1)
        bf.reset_chrome_detect_cache()
        with mock.patch.object(bf, "probe_cdp", return_value=False), mock.patch.object(
            bf, "playwright_installed", return_value=True
        ) as m2:
            self.assertFalse(bf.chrome_available())
            self.assertFalse(bf.chrome_available())
            self.assertEqual(m2.call_count, 1)
        bf.reset_chrome_detect_cache()

    def test_chrome_available_requires_playwright(self) -> None:
        """CDP 可达但缺 Playwright 时，chrome_available 应为 False（auto 走 API）。"""
        from unittest import mock

        from app.scrapers import browser_fallback as bf

        bf.reset_chrome_detect_cache()
        with mock.patch.object(bf, "probe_cdp", return_value=True), mock.patch.object(
            bf, "playwright_installed", return_value=False
        ):
            self.assertFalse(bf.chrome_available())
        bf.reset_chrome_detect_cache()

    def test_describe_modes_auto_hint(self) -> None:
        """auto 文案应体现「检测 Chrome 优先」。"""
        from app.scrapers.mode import MODE_AUTO, describe_modes

        auto = next(i for i in describe_modes() if i["value"] == MODE_AUTO)
        self.assertIn("Chrome", auto["hint"])

    def test_book_list_item_title_alias(self) -> None:
        """列表项 name 与 title 同值，契约统一。"""
        from app.models import Book
        from app.serializers import book_list_item

        b = Book(id=1, title="测试书", author="作者", category="都市", tags="", intro="")
        data = book_list_item(b)
        self.assertEqual(data["name"], "测试书")
        self.assertEqual(data["title"], "测试书")
        # 有封面时同时给出原图与缩略图地址
        b2 = Book(
            id=2, title="有封面", author="作者", category="都市",
            tags="", intro="", cover_file="1_1.jpg",
        )
        data2 = book_list_item(b2)
        self.assertEqual(data2["cover_thumb_path"], "/thumbs/1_1.jpg?w=320")
        self.assertTrue(data2["cover_thumb_url"].endswith("/thumbs/1_1.jpg?w=320"))
        # 最近阅读时间随列表返回，供「继续阅读」使用
        self.assertEqual(data["read_at"], "")


if __name__ == "__main__":
    unittest.main()
