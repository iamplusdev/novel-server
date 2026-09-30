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
        # 对外地址：前端入口（浏览器/手机访问）
        self.public_base_url: str = _env("PUBLIC_BASE_URL", "http://127.0.0.1:7311").rstrip("/")
        self.host: str = _env("HOST", "0.0.0.0")
        # 后端 API 端口（run.py 同时拉起前端静态服务）
        self.port: int = int(_env("PORT", "7312"))
        # 前端静态/反代端口（同源 Cookie 靠此端口转发 /api）
        self.frontend_port: int = int(_env("FRONTEND_PORT", "7311"))
        self.novels_dir: Path = _path("NOVELS_DIR", BASE_DIR / "novels")
        self.database_path: Path = _path("DATABASE_PATH", BASE_DIR / "data" / "novels.db")
        self.covers_dir: Path = _path("COVERS_DIR", BASE_DIR / "covers")
        # 章节正文包目录：与 DB 同卷持久化，但备份 zip 不打包（可从源 TXT 重建）
        self.contents_dir: Path = _path("CONTENTS_DIR", self.database_path.parent / "contents")
        self.database_url: str = f"sqlite:///{self.database_path}"
        # HTTPS / 反代场景请设 COOKIE_SECURE=1，会话 Cookie 才带 Secure
        self.cookie_secure: bool = _env("COOKIE_SECURE", "0").lower() in ("1", "true", "yes", "on")

    def ensure_dirs(self) -> None:
        self.novels_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.contents_dir.mkdir(parents=True, exist_ok=True)


# 允许删除的封面图片扩展名（源 TXT 等其它文件永不删除）
ALLOWED_COVER_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def safe_delete_cover(cover_file: str) -> bool:
    """仅删除 covers 目录内的封面图片；拒绝 txt / 路径穿越 / 非图片。

    删除书籍只清库内数据 + 封面图，绝不触碰 novels/ 下源 TXT。
    """
    name = (cover_file or "").strip()
    if not name:
        return False
    # 禁止路径分隔与盘符，防止误删 novels/ 或其它目录下的 txt
    if any(ch in name for ch in ("/", "\\", ":")) or name.startswith("."):
        return False
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_COVER_IMG_EXT:
        return False
    covers_dir = settings.covers_dir.resolve()
    path = (covers_dir / name).resolve()
    # 必须落在 covers 目录内
    if path.parent != covers_dir:
        return False
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


# 未分类（既是分类名，也是 tags 标记）
UNCATEGORIZED = "未分类"

# 全站统一分类标准：以起点 15 类为准（书源前缀仍区分起点/番茄/纵横/本地）
QIDIAN_CATEGORIES = [
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

# 书源 → 分类选项（统一为起点 15 类）；本地/WebDAV 目录：novels/<书源>/<分类>/
SOURCE_CATEGORIES: dict[str, list[str]] = {
    "起点": QIDIAN_CATEGORIES,
    "番茄": QIDIAN_CATEGORIES,
    "纵横": QIDIAN_CATEGORIES,
}

# 兼容旧代码/旧数据的扁平分类名（不含书源前缀）
LEGACY_CATEGORIES = list(QIDIAN_CATEGORIES)

# 风格标签：只进 tags，不作分类（第一人称/开局等）
STYLE_ONLY_TAGS = {
    "第一人称",
    "开局",
    "搞笑轻松",
    "断层",
}


# 书源别名 → 标准名
_SOURCE_ALIASES = {
    "qidian": "起点",
    "fanqie": "番茄",
    "zongheng": "纵横",
    "起点": "起点",
    "番茄": "番茄",
    "纵横": "纵横",
}


def normalize_source(source: str) -> str:
    return _SOURCE_ALIASES.get((source or "").strip().lower(), (source or "").strip())


def make_category_label(source: str, site_cat: str) -> str:
    """拼成展示/存储用分类：「起点-都市」「番茄-都市」；无书源则保留原名。"""
    cat = (site_cat or "").strip()
    if not cat or cat == UNCATEGORIZED:
        return UNCATEGORIZED
    src, rest = parse_category_label(cat)
    if src:
        return f"{src}-{rest}"
    src_name = normalize_source(source)
    if src_name in SOURCE_CATEGORIES:
        return f"{src_name}-{cat}"
    return cat


def parse_category_label(label: str) -> tuple[str, str]:
    """「番茄-都市」→ (番茄, 都市)；「都市」→ ("", 都市)。"""
    s = (label or "").strip()
    if not s:
        return "", UNCATEGORIZED
    for sep in ("-", "/", "·"):
        for src in SOURCE_CATEGORIES:
            prefix = src + sep
            if s.startswith(prefix) and len(s) > len(prefix):
                return src, s[len(prefix) :].strip() or UNCATEGORIZED
    return "", s


# 各站栏目/历史别名 → 起点标准分类（一对多统一落默认：玄幻奇幻→玄幻、武侠仙侠→仙侠、游戏体育→游戏）
_SITE_CAT_TO_QIDIAN: dict[str, str] = {
    # —— 起点旧别名 ——
    "玄幻奇幻": "玄幻",
    "奇幻玄幻": "玄幻",
    "东方玄幻": "玄幻",
    "异世大陆": "奇幻",
    "异界大陆": "奇幻",
    "转世重生": "奇幻",
    "武侠仙侠": "仙侠",
    "修真": "仙侠",
    "修仙": "仙侠",
    "仙侠修真": "仙侠",
    "奇幻仙侠": "仙侠",
    "都市现实": "都市",
    "都市生活": "都市",
    "高武": "都市",
    "历史军事": "历史",
    "古代": "历史",
    "游戏体育": "游戏",
    "科幻灵异": "科幻",
    "未来": "科幻",
    "诸天": "诸天无限",
    "无限流": "诸天无限",
    "悬疑": "悬疑灵异",
    "灵异": "悬疑灵异",
    "女频": "轻小说",
    "言情": "轻小说",
    "男频": "玄幻",
    "现代": "现实",
    # —— 番茄站内栏目 ——
    "西方奇幻": "奇幻",
    "东方仙侠": "仙侠",
    "科幻末世": "科幻",
    "都市日常": "都市",
    "都市修真": "仙侠",
    "都市高武": "都市",
    "历史古代": "历史",
    "战神赘婿": "都市",
    "都市种田": "都市",
    "传统玄幻": "玄幻",
    "历史脑洞": "历史",
    "悬疑脑洞": "悬疑灵异",
    "都市脑洞": "都市",
    "玄幻脑洞": "玄幻",
    "抗战谍战": "军事",
    "动漫衍生": "诸天无限",
    "男频衍生": "诸天无限",
    "衍生": "诸天无限",
    "双男主": "诸天无限",
    "女频衍生": "诸天无限",
    # —— 番茄细分/频道 ——
    "仕途": "都市",
    "综影视": "诸天无限",
    "综漫": "诸天无限",
    "天灾": "科幻",
    "赛博朋克": "科幻",
    "第四天灾": "游戏",
    "规则怪谈": "悬疑灵异",
    "克苏鲁": "悬疑灵异",
    "都市异能": "都市",
    "末日求生": "科幻",
    "灵气复苏": "玄幻",
    "高武世界": "都市",
    "谍战": "军事",
    "清朝": "历史",
    "宋朝": "历史",
    "武将": "军事",
    "国运": "军事",
    "架空": "历史",
    "架空历史": "历史",
    "穿越历史": "历史",
    # —— 纵横站内栏目 ——
    "奇闻异事": "悬疑灵异",
    "N次元": "轻小说",
    "现实题材": "现实",
    "玄幻小说": "玄幻",
    "奇幻小说": "奇幻",
    "武侠小说": "武侠",
    "仙侠小说": "仙侠",
    "传统武侠": "武侠",
    "竞技": "体育",
    "电子竞技": "游戏",
    "同人": "诸天无限",
    "女生": "轻小说",
    "二次元": "轻小说",
    "写实": "现实",
    "军史": "军事",
    "战争": "军事",
}


def _match_in_list(raw: str, cats: list[str]) -> str:
    """精确优先，其次最长包含（避免「武侠仙侠」误成「武侠」）。"""
    if raw in cats:
        return raw
    best = ""
    for c in cats:
        if c in raw or raw in c:
            if not best or len(c) > len(best):
                best = c
    return best


def to_qidian_category(raw: str) -> str:
    """任意站内分类/别名 → 起点 15 类；风格标签/未知 → 空串。

    - 风格标签（第一人称/开局等）只进 tags，不作分类
    - 一对多（玄幻奇幻/武侠仙侠/游戏体育）统一落默认起点分类
    """
    s = (raw or "").strip()
    if not s or s == UNCATEGORIZED or s in STYLE_ONLY_TAGS:
        return ""
    if s in QIDIAN_CATEGORIES:
        return s
    mapped = _SITE_CAT_TO_QIDIAN.get(s) or _SITE_CAT_TO_QIDIAN.get(s.replace("小说", ""))
    if mapped in QIDIAN_CATEGORIES:
        return mapped
    # 最长包含兜底（「都市日常」→「都市」）
    return _match_in_list(s, QIDIAN_CATEGORIES)


def map_site_category(source: str, raw: str) -> tuple[str, str]:
    """刮削/手动分类 → (书源标准名, 起点标准分类)。

    - 分类维度统一为起点 15 类（番茄/纵横原栏目自动映射）
    - 有书源：保留书源前缀（起点-都市 / 番茄-都市）
    - 无书源（本地）：扁平分类，不贴书源前缀
    - 风格标签/未知 → 未分类（原词保留在 tags）
    """
    src = normalize_source(source)
    cat = (raw or "").strip()
    psrc, prest = parse_category_label(cat)
    if psrc:
        src = psrc or src
        cat = prest
    if not cat or cat == UNCATEGORIZED:
        return src, UNCATEGORIZED

    q = to_qidian_category(cat)
    return src, (q or UNCATEGORIZED)


def category_tree() -> list[dict]:
    """编辑页两级分类数据：书源列表 + 统一的起点 15 类。"""
    return [
        {"key": "", "label": "本地", "categories": list(LEGACY_CATEGORIES) + [UNCATEGORIZED]},
        {"key": "起点", "label": "起点", "categories": list(QIDIAN_CATEGORIES)},
        {"key": "番茄", "label": "番茄", "categories": list(QIDIAN_CATEGORIES)},
        {"key": "纵横", "label": "纵横", "categories": list(QIDIAN_CATEGORIES)},
    ]


def category_rel_parts(label: str) -> tuple[str, ...]:
    """分类值 → novels 相对目录层级：番茄-都市 → (番茄, 都市)。"""
    src, cat = parse_category_label(label)
    if src:
        return (src, cat or UNCATEGORIZED)
    return (cat or UNCATEGORIZED,)


def all_category_labels() -> list[str]:
    """管理端/公开 API 的分类选项全集（书源两级 + 未分类）。"""
    opts: list[str] = []
    for src, cats in SOURCE_CATEGORIES.items():
        for c in cats:
            opts.append(f"{src}-{c}")
    # 旧扁平分类，便于未搬家数据筛选
    for c in LEGACY_CATEGORIES:
        if c not in opts:
            opts.append(c)
    opts.append(UNCATEGORIZED)
    return opts


# 分类选项（含书源前缀）；旧代码 import CATEGORIES 仍可用
CATEGORIES = all_category_labels()

settings = Settings()
