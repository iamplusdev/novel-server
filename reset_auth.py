#!/usr/bin/env python3
"""服务端紧急重置管理账号（忘记恢复码时使用）。

用法:
  python reset_auth.py              # 用户名 admin，随机密码 + 新恢复码
  python reset_auth.py myname       # 指定用户名
  python reset_auth.py myname pass  # 指定用户名与密码（至少 6 位）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.auth import reset_account_cli  # noqa: E402


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    password = sys.argv[2] if len(sys.argv) > 2 else ""
    recovery = reset_account_cli(username, password)
    print("账号已重置")
    print(f"  用户名: {username}")
    print(f"  密码:   {password if password else '(随机，见 auth.json 不可读——请用恢复码重设或重新运行并指定密码)'}")
    if not password:
        print("  提示:   未指定密码，请用下面恢复码在「忘记密码」中设置，或重跑: python reset_auth.py 用户名 密码")
    print(f"  恢复码: {recovery}")
    print("请立即保存恢复码，离开本界面后无法再次查看。")


if __name__ == "__main__":
    main()
