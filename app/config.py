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
        # HTTPS / 反代场景请设 COOKIE_SECURE=1，会话 Cookie 才带 Secure
        self.cookie_secure: bool = _env("COOKIE_SECURE", "0").lower() in ("1", "true", "yes", "on")

    def ensure_dirs(self) -> None:
        self.novels_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


# 未分类（既是分类名，也是 tags 标记）
UNCATEGORIZED = "未分类"

# 书源 → 站内分类（与官网栏目一致）；本地/WebDAV 目录：novels/<书源>/<分类>/
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

FANQIE_CATEGORIES = [
    "西方奇幻",
    "东方仙侠",
    "科幻末世",
    "都市日常",
    "都市修真",
    "都市高武",
    "历史古代",
    "战神赘婿",
    "都市种田",
    "传统玄幻",
    "历史脑洞",
    "悬疑脑洞",
    "都市脑洞",
    "玄幻脑洞",
    "悬疑灵异",
    "抗战谍战",
    "游戏体育",
    "动漫衍生",
    "男频衍生",
]

SOURCE_CATEGORIES: dict[str, list[str]] = {
    "起点": QIDIAN_CATEGORIES,
    "番茄": FANQIE_CATEGORIES,
}

# 兼容旧代码/旧数据的扁平分类名（不含书源前缀）
LEGACY_CATEGORIES = list(QIDIAN_CATEGORIES)


# 书源别名 → 标准名
_SOURCE_ALIASES = {
    "qidian": "起点",
    "fanqie": "番茄",
    "起点": "起点",
    "番茄": "番茄",
}


def normalize_source(source: str) -> str:
    return _SOURCE_ALIASES.get((source or "").strip().lower(), (source or "").strip())


def make_category_label(source: str, site_cat: str) -> str:
    """拼成展示/存储用分类：「起点-都市」「番茄-西方奇幻」；无书源则保留原名。"""
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
    """「番茄-西方奇幻」→ (番茄, 西方奇幻)；「都市」→ ("", 都市)。"""
    s = (label or "").strip()
    if not s:
        return "", UNCATEGORIZED
    for sep in ("-", "/", "·"):
        for src in SOURCE_CATEGORIES:
            prefix = src + sep
            if s.startswith(prefix) and len(s) > len(prefix):
                return src, s[len(prefix) :].strip() or UNCATEGORIZED
    return "", s


# 站内/历史别名 → 起点标准栏目（刮削与手动挂类共用）
_QIDIAN_CAT_ALIAS = {
    "玄幻奇幻": "玄幻",
    "奇幻玄幻": "玄幻",
    "东方玄幻": "玄幻",
    "异世大陆": "奇幻",
    "武侠仙侠": "仙侠",
    "修真": "仙侠",
    "修仙": "仙侠",
    "仙侠修真": "仙侠",
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
    "轻小说": "轻小说",
    "女频": "轻小说",
    "言情": "轻小说",
    "男频": "玄幻",
    "现代": "现实",
    "短篇": "短篇",
}

# 番茄站内别名（与 scrapers/fanqie 对齐）
_FANQIE_CAT_ALIAS = {
    "衍生": "男频衍生",
    "双男主": "男频衍生",
    "女频衍生": "动漫衍生",
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


def map_site_category(source: str, raw: str) -> tuple[str, str]:
    """刮削/手动分类 → (书源标准名, 站内分类)。

    - 有书源（起点/番茄）：归到该源栏目（别名/包含可匹配）
    - 无书源（本地）：只归到扁平分类，**不**自动贴书源前缀
    """
    src = normalize_source(source)
    cat = (raw or "").strip()
    psrc, prest = parse_category_label(cat)
    if psrc:
        src = psrc or src
        cat = prest
    if not cat or cat == UNCATEGORIZED:
        return src, UNCATEGORIZED

    # 指定书源：别名 → 精确/包含
    if src in SOURCE_CATEGORIES:
        cats = SOURCE_CATEGORIES[src]
        if src == "起点":
            alias = _QIDIAN_CAT_ALIAS.get(cat) or _QIDIAN_CAT_ALIAS.get(cat.replace("小说", ""))
            if alias in cats:
                return src, alias
        if src == "番茄":
            alias = _FANQIE_CAT_ALIAS.get(cat)
            if alias in cats:
                return src, alias
        hit = _match_in_list(cat, cats)
        if hit:
            return src, hit
        return src, cat

    # 本地/无书源：对齐扁平分类即可
    legacy = list(LEGACY_CATEGORIES) + [UNCATEGORIZED]
    hit = _match_in_list(cat, legacy)
    return "", (hit or cat)


def category_tree() -> list[dict]:
    """编辑页两级分类数据：书源列表 + 各自栏目。"""
    return [
        {"key": "", "label": "本地", "categories": list(LEGACY_CATEGORIES) + [UNCATEGORIZED]},
        {"key": "起点", "label": "起点", "categories": list(QIDIAN_CATEGORIES)},
        {"key": "番茄", "label": "番茄", "categories": list(FANQIE_CATEGORIES)},
    ]


def category_rel_parts(label: str) -> tuple[str, ...]:
    """分类值 → novels 相对目录层级：番茄-西方奇幻 → (番茄, 西方奇幻)。"""
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
