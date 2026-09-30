"""刮削源注册表（按需导入，降低启动 RSS）。

qidian/fanqie/zongheng 体积较大，仅在首次真正刮削时才 import。
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

SOURCE_LABELS = {
    "qidian": "起点",
    "fanqie": "番茄",
    "zongheng": "纵横",
    "起点": "起点",
    "番茄": "番茄",
    "纵横": "纵横",
}

ALL_SOURCES = ("qidian", "fanqie", "zongheng")

# 别名 → 模块名
_MOD_NAMES = {
    "qidian": "qidian",
    "起点": "qidian",
    "fanqie": "fanqie",
    "番茄": "fanqie",
    "zongheng": "zongheng",
    "纵横": "zongheng",
}


class LazyRegistry:
    """dict 风格的刮削源表：get/__getitem__ 时才加载对应模块。"""

    def __init__(self) -> None:
        self._mods: dict[str, Any] = {}

    def _load(self, key: str) -> Any | None:
        name = _MOD_NAMES.get(key) or (key if key in ALL_SOURCES else None)
        if name is None:
            return None
        if name not in self._mods:
            self._mods[name] = import_module(f".{name}", __name__)
        return self._mods[name]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self._load(str(key))
        except Exception:  # noqa: BLE001
            return default

    def __getitem__(self, key: str) -> Any:
        mod = self._load(str(key))
        if mod is None:
            raise KeyError(key)
        return mod

    def __contains__(self, key: object) -> bool:
        return str(key) in _MOD_NAMES or str(key) in ALL_SOURCES


REGISTRY = LazyRegistry()
