"""刮削源注册表。"""
from __future__ import annotations

from . import fanqie, qidian

REGISTRY = {
    "qidian": qidian,
    "起点": qidian,
    "fanqie": fanqie,
    "番茄": fanqie,
}

SOURCE_LABELS = {
    "qidian": "起点",
    "fanqie": "番茄",
    "起点": "起点",
    "番茄": "番茄",
}

ALL_SOURCES = ("qidian", "fanqie")
