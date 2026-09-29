"""统一日志配置：控制台 + 可选文件，供 run.py / app.main 调用。"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import settings

_configured = False


def setup_logging() -> None:
    """初始化根日志；重复调用无副作用。"""
    global _configured
    if _configured:
        return

    level_name = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # 清掉无 handler 的重复挂载（热重载场景）
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # 可选落盘：LOG_FILE=1 或指定路径
    log_file = (os.environ.get("LOG_FILE") or "").strip()
    if log_file and log_file.lower() not in ("0", "false", "no"):
        path = settings.database_path.parent / "novel-server.log"
        if log_file.lower() not in ("1", "true", "yes", "on"):
            path = settings.database_path.parent / log_file
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # 降低第三方噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
