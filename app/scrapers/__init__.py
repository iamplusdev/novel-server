"""刮削源注册表。"""
from __future__ import annotations

from . import fanqie, qidian, zongheng

REGISTRY = {
    "qidian": qidian,
    "起点": qidian,
    "fanqie": fanqie,
    "番茄": fanqie,
    "zongheng": zongheng,
    "纵横": zongheng,
}

SOURCE_LABELS = {
    "qidian": "起点",
    "fanqie": "番茄",
    "zongheng": "纵横",
    "起点": "起点",
    "番茄": "番茄",
    "纵横": "纵横",
}

ALL_SOURCES = ("qidian", "fanqie", "zongheng")
