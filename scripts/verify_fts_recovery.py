"""验证 FTS 不同步自愈：模拟远程「database disk image is malformed」场景。

1. 建库 + 建一本书
2. 手动删掉 books_fts 中该书的行（模拟索引漂移，远程线上状态）
3. PUT progress → 期望：自动重建 FTS 并成功返回 200（旧代码会 500）
4. 再验证 PATCH book 与搜索（FTS 路径）正常
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_PATH"] = str(tmp / "novels.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import engine, SessionLocal  # noqa: E402
from app.models import Book  # noqa: E402

client = TestClient(app)

# 1) 初始化账号
r = client.post("/api/auth/setup", json={"username": "tester", "password": "test123456"})
assert r.status_code == 200, r.text
H = {"Authorization": f"Bearer {r.json()['token']}"}

# 2) 直接插一本书
with SessionLocal() as db:
    b = Book(title="测试书", author="作者", category="", status="finished")
    db.add(b)
    db.commit()
    bid = b.id
print(f"[setup] book id={bid}")

# 3) 制造 FTS 与 books 不同步：删掉 FTS 里的这一行
with engine.begin() as conn:
    n = conn.exec_driver_sql(f"DELETE FROM books_fts WHERE rowid={bid}").rowcount
print(f"[desync] removed {n} row(s) from books_fts")
assert n == 1

# 4) PUT progress：旧代码在此处 500（malformed），修复后应自动恢复并 200
r = client.put(
    f"/api/admin/books/{bid}/progress",
    json={"percent": 2, "chapter_index": 20},
    headers=H,
)
print(f"[PUT progress] {r.status_code} {r.text[:150]}")
assert r.status_code == 200, "修复失败：PUT progress 仍报错"
assert r.json()["read_chapter_index"] == 20

# 5) FTS 已被自愈重建：验证行回来了
with engine.begin() as conn:
    rows = conn.exec_driver_sql("SELECT rowid FROM books_fts").fetchall()
print(f"[fts] after recovery rowids={[r[0] for r in rows]}")
assert [r[0] for r in rows] == [bid]

# 6) PATCH book（同样走 UPDATE 触发器）
r = client.patch(f"/api/admin/books/{bid}", json={"intro": "简介更新"}, headers=H)
print(f"[PATCH book] {r.status_code} {str(r.text)[:120]}")
assert r.status_code == 200

# 7) 搜索走 FTS 正常
r = client.get("/api/admin/books", params={"q": "测试"}, headers=H)
print(f"[search] {r.status_code}, items={len(r.json().get('items', []))}")
assert r.status_code == 200

# 8) 重复 PUT progress（恢复后常规路径）
r = client.put(f"/api/admin/books/{bid}/progress", json={"percent": 5}, headers=H)
assert r.status_code == 200 and r.json()["read_percent"] == 5
print("[PUT again] OK")

print("\nALL PASS ✅  FTS desync auto-recovery works")
