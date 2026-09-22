"""刮削源注册表。后续可加番茄等。"""
from __future__ import annotations

from . import qidian

# source key -> module
REGISTRY = {
    "qidian": qidian,
    "起点": qidian,
}

SOURCE_LABELS = {
    "qidian": "起点",
}
