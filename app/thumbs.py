"""封面缩略图（可选依赖 Pillow）：按需生成并落盘缓存，缺失时回退原图。

设计：
- 未安装 Pillow / 源图损坏 / 生成失败 → 返回 None，由调用方回退原封面
- 缩略图存 covers/thumbs/{原文件名去扩展}_{宽度}.webp
- 生成走临时文件 + replace，避免并发/中断留下半截文件
"""
from __future__ import annotations

import threading
from pathlib import Path

from .config import ALLOWED_COVER_IMG_EXT, settings

try:  # 可选依赖：未安装时完全不影响现有封面展示
    from PIL import Image, ImageOps
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

DEFAULT_WIDTH = 320
MIN_WIDTH = 120
MAX_WIDTH = 800
THUMB_SUBDIR = "thumbs"


def clamp_width(width: int | str | None) -> int:
    """宽度夹紧到安全区间，非法值回退默认宽度。"""
    try:
        w = int(width)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, w))


def _safe_name(name: str) -> str:
    """校验封面文件名：禁止路径分隔/盘符/隐藏文件，仅允许图片扩展名。"""
    n = (name or "").strip()
    if not n or any(ch in n for ch in ("/", "\\", ":")) or n.startswith("."):
        return ""
    if Path(n).suffix.lower() not in ALLOWED_COVER_IMG_EXT:
        return ""
    return n


def thumbs_dir() -> Path:
    d = settings.covers_dir / THUMB_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_cover_path(name: str) -> Path | None:
    """原封面路径（已校验必须落在 covers 目录内）；用于生成失败时回退。"""
    safe = _safe_name(name)
    if not safe:
        return None
    covers_dir = settings.covers_dir.resolve()
    path = (covers_dir / safe).resolve()
    if path.parent != covers_dir:
        return None
    return path


def ensure_thumb(name: str, width: int = DEFAULT_WIDTH) -> Path | None:
    """确保缩略图存在并返回路径；不可用时返回 None（调用方回退原图）。"""
    safe = _safe_name(name)
    if not safe or Image is None or ImageOps is None:
        return None
    src = safe_cover_path(safe)
    if src is None or not src.is_file():
        return None

    w = clamp_width(width)
    dest = thumbs_dir() / f"{Path(safe).stem}_{w}.webp"
    try:
        # 原图未更新时直接复用缓存
        if dest.is_file() and dest.stat().st_mtime_ns >= src.stat().st_mtime_ns:
            return dest
    except OSError:
        pass

    tmp = dest.with_name(f"{dest.name}.{threading.get_ident()}.tmp")
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((w, w * 2), Image.Resampling.LANCZOS)
            # 统一色彩模式，避免 RGBA/P/CMYK 写 webp 失败
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            im.save(tmp, format="WEBP", quality=82, method=4)
        tmp.replace(dest)
        return dest
    except Exception:  # noqa: BLE001
        try:
            tmp.unlink()
        except OSError:
            pass
        return None


def delete_thumbs_for(name: str) -> int:
    """删除某个封面派生出的全部缩略图（换封面/删书时调用）。"""
    safe = _safe_name(name)
    if not safe:
        return 0
    d = settings.covers_dir / THUMB_SUBDIR
    if not d.is_dir():
        return 0
    removed = 0
    prefix = f"{Path(safe).stem}_"
    # 逐个匹配而非 glob：避免文件名里的通配符元字符改变匹配语义
    for path in d.iterdir():
        if path.suffix.lower() == ".webp" and path.name.startswith(prefix):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
