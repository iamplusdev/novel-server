#!/usr/bin/env python3
"""启动服务器：python run.py

端口约定（生产/本地同一套）：
  - 后端 API  : PORT          默认 7312
  - 前端入口  : FRONTEND_PORT 默认 7311（同一 ASGI 应用：静态 + /api）

开发时前端也可用 Vite：cd frontend && npm run dev（默认 5173，代理到 7312）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

from app.config import settings
from app.database import init_db
from app.frontend_server import start_in_thread as start_frontend
from app.importer import ensure_category_dirs
from app.logging_setup import setup_logging

# 前端构建产物（与仓库结构绑定）
DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def main() -> None:
    setup_logging()
    settings.ensure_dirs()
    ensure_category_dirs()
    init_db()

    api_host = settings.host

    print("Novel Library")
    print(f"  前端入口    http://{api_host}:{settings.frontend_port}/  (管理后台)")
    print(f"  后端 API    http://{api_host}:{settings.port}/  (/api /covers /health)")
    print(f"  Public base {settings.public_base_url}")
    print(f"  Novels dir  {settings.novels_dir}")
    print(f"  Database    {settings.database_path}")
    if not (DIST_DIR / "index.html").is_file():
        print(
            "  [警告] 未找到 frontend/dist，请先构建：cd frontend && npm install && npm run build",
            file=sys.stderr,
        )

    # 前端入口端口：同一 FastAPI app（静态 + API 同源），守护线程监听
    from app.main import app

    start_frontend(app=app, host=api_host, port=settings.frontend_port)

    # 后端 API 端口（主线程阻塞）
    uvicorn.run(app, host=api_host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
