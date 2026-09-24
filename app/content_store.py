"""章节正文包：一本书一个 UTF-8 文件，章节只存字节偏移/长度。

热数据（书目、章节标题、偏移）留在 SQLite；冷正文写入 data/contents/{book_id}.bin，
读章时按偏移切片。备份只含小 DB + 封面，正文包可从源 TXT / 重新导入重建。
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Sequence

from .config import settings

# 最近读过的章节小缓存，避免同章反复 seek（容量按章数估算，章均几十 KB）
_CACHE_MAX = 32
_cache: OrderedDict[tuple[int, int], str] = OrderedDict()
_cache_lock = Lock()


def contents_dir() -> Path:
    """正文包目录（挂在 data/ 下，随数据卷持久化，但不进备份 zip）。"""
    d = settings.contents_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def content_pack_path(book_id: int) -> Path:
    return contents_dir() / f"{int(book_id)}.bin"


def write_pack(book_id: int, texts: Sequence[str]) -> list[tuple[int, int, int]]:
    """把各章正文顺序写入正文包，返回 [(byte_offset, byte_len, char_len), ...]。

    原子落盘（先写 .tmp 再替换），避免半截包被读到。
    """
    buf = bytearray()
    spans: list[tuple[int, int, int]] = []
    for t in texts:
        raw = (t or "").encode("utf-8")
        spans.append((len(buf), len(raw), len(t or "")))
        buf.extend(raw)

    path = content_pack_path(book_id)
    tmp = path.with_suffix(".bin.tmp")
    tmp.write_bytes(bytes(buf))
    tmp.replace(path)
    # 重写后旧缓存失效
    _invalidate_book(book_id)
    return spans


def read_chapter_text(
    book_id: int,
    offset: int,
    length: int,
    legacy_content: str | None = None,
) -> str:
    """按偏移读一章；无偏移时回退旧版 content 列（迁移前数据）。"""
    if length and length > 0:
        key = (int(book_id), int(offset))
        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None:
                _cache.move_to_end(key)
                return hit
        path = content_pack_path(book_id)
        if not path.is_file():
            return legacy_content or ""
        with path.open("rb") as f:
            f.seek(int(offset))
            raw = f.read(int(length))
        text = raw.decode("utf-8", errors="replace")
        with _cache_lock:
            _cache[key] = text
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        return text
    return legacy_content or ""


def read_book_texts(book_id: int, spans: Sequence[tuple[int, int]]) -> list[str]:
    """按 (offset, length) 列表读整本书章节（体检/修复用）。"""
    path = content_pack_path(book_id)
    out: list[str] = []
    if not path.is_file():
        return ["" for _ in spans]
    data = path.read_bytes()
    for off, ln in spans:
        if ln and ln > 0:
            out.append(data[off : off + ln].decode("utf-8", errors="replace"))
        else:
            out.append("")
    return out


def delete_pack(book_id: int) -> bool:
    """删除一本书的正文包（删书时调用）。"""
    _invalidate_book(book_id)
    path = content_pack_path(book_id)
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _invalidate_book(book_id: int) -> None:
    bid = int(book_id)
    with _cache_lock:
        for key in [k for k in _cache if k[0] == bid]:
            _cache.pop(key, None)
