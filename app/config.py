"""极简配置：环境变量 + 项目根目录默认值，零额外依赖。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip() or default


def _path(key: str, default: Path) -> Path:
    raw = _env(key, str(default))
    p = Path(raw)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    return p


class Settings:
    def __init__(self) -> None:
        self.public_base_url: str = _env("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self.host: str = _env("HOST", "0.0.0.0")
        self.port: int = int(_env("PORT", "8000"))
        self.novels_dir: Path = _path("NOVELS_DIR", BASE_DIR / "novels")
        self.database_path: Path = _path("DATABASE_PATH", BASE_DIR / "data" / "novels.db")
        self.covers_dir: Path = _path("COVERS_DIR", BASE_DIR / "covers")
        self.database_url: str = f"sqlite:///{self.database_path}"

    def ensure_dirs(self) -> None:
        self.novels_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


# 小说分类（与文件夹名一致）
CATEGORIES = [
    "玄幻",
    "奇幻",
    "武侠",
    "仙侠",
    "都市",
    "现实",
    "军事",
    "历史",
    "游戏",
    "体育",
    "科幻",
    "诸天无限",
    "悬疑灵异",
    "轻小说",
    "短篇",
]

settings = Settings()
