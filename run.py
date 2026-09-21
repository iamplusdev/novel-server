#!/usr/bin/env python3
"""启动服务器：python run.py"""
from __future__ import annotations

import uvicorn

from app.config import settings
from app.database import init_db
from app.importer import ensure_category_dirs


def main() -> None:
    settings.ensure_dirs()
    ensure_category_dirs()
    init_db()
    print(f"Novel Library  http://{settings.host}:{settings.port}")
    print(f"Admin          http://{settings.host}:{settings.port}/admin")
    print(f"Public base    {settings.public_base_url}")
    print(f"Novels dir     {settings.novels_dir}")
    print(f"Database       {settings.database_path}")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
