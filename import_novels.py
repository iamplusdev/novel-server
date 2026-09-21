#!/usr/bin/env python3
"""CLI 导入器：python import_novels.py [--watch]

扫描 NOVELS_DIR 下按分类存放的 .txt，解析章节后写入 SQLite。
相同文件内容（SHA256）会跳过。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 保证可从项目根导入 app
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.importer import ensure_category_dirs, import_all  # noqa: E402


def run_once() -> int:
    init_db()
    ensure_category_dirs()
    print(f"扫描目录: {settings.novels_dir}")
    print(f"数据库:   {settings.database_path}")
    result = import_all()
    print(result.summary)
    if result.added:
        print("新增:")
        for x in result.added:
            print(f"  + {x}")
    if result.updated:
        print("更新:")
        for x in result.updated:
            print(f"  ~ {x}")
    if result.failed:
        print("失败:")
        for x in result.failed:
            print(f"  ! {x}")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 TXT 小说到 SQLite")
    parser.add_argument("--watch", action="store_true", help="监视目录并定期增量导入")
    parser.add_argument("--interval", type=int, default=300, help="watch 模式间隔秒数")
    args = parser.parse_args()

    if args.watch:
        print(f"watch 模式，每 {args.interval}s 扫描一次… Ctrl+C 退出")
        while True:
            try:
                run_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"导入出错: {exc}", file=sys.stderr)
            time.sleep(args.interval)
    else:
        code = run_once()
        raise SystemExit(code)


if __name__ == "__main__":
    main()
