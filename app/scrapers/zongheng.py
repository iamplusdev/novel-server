"""纵横中文网刮削（标准库 JSON/HTML 解析，仅元数据，不抓正文）。

搜索: https://search.zongheng.com/search/book?keyword=...
详情: https://www.zongheng.com/detail/{bookId}
"""
from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse

from ..config import to_qidian_category
from .http_util import HttpError, http_get as _http_get_raw, http_get_bytes
from .qidian import ScrapeError, ScrapeHit, clean_tag_token

SOURCE_NAME = "纵横"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 20
_SEARCH_API = "https://search.zongheng.com/search/book"


def map_category(raw: str) -> str:
    """纵横原栏目/别名 → 起点 15 类；未知返回空串（由写库侧落未分类）。"""
    return to_qidian_category(raw)


def _http_get(url: str, headers: dict | None = None) -> str:
    """统一走 http_util。"""
    try:
        return _http_get_raw(
            url,
            headers=headers or {"Referer": "https://www.zongheng.com/"},
            timeout=TIMEOUT,
            referer="https://www.zongheng.com/",
        )
    except HttpError as e:
        raise ScrapeError(f"纵横{e}") from e


def _clean(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _is_seo_intro(text: str) -> bool:
    """识别站点 SEO 文案，不当作真实简介。"""
    s = (text or "")
    if not s:
        return True
    bad = (
        "纵横小说网提供",
        "全文阅读服务",
        "无弹窗广告",
        "欢迎光临",
        "纵横中文网为您",
        "无广告、无弹窗",
        "最新章节全文阅读",
        "免费阅读",
    )
    return any(b in s for b in bad)


def _is_junk_tag(t: str, book_name: str = "") -> bool:
    """过滤分类名、状态、SEO 词、书名碎片。"""
    s = (t or "").strip()
    if not s or len(s) > 12:
        return True
    if s in ("开始阅读", "连载", "完结", "已完结", "完本", "未知"):
        return True
    # 纵横一级栏目名不当标签（「异界」等风格词保留）
    if s in _ZH_PARENT_CATS:
        return True
    junk_sub = ("全集", "免费阅读", "最新章节", "小说", "在线阅读", "无弹窗", "TXT", "txt")
    if any(j in s for j in junk_sub):
        return True
    if book_name and s in book_name:
        return True
    return False


def _strip_font(name: str) -> str:
    """去掉搜索高亮 <font color="RED">…</font>。"""
    return _clean(name)


def cover_url_for(book_id: str) -> str:
    # 无稳定直链时用详情页；有 coverUrl 则覆盖
    return book_url_for(book_id)


def book_url_for(book_id: str) -> str:
    return f"https://www.zongheng.com/detail/{book_id}"


def extract_book_id(text: str) -> str:
    s = (text or "").strip()
    m = re.search(r"zongheng\.com/(?:detail|book)/(\d{5,16})", s)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\d{5,16})", s)
    return m.group(1) if m else ""


def _status_from_serial(code) -> str:
    # 捕获样本: 0→连载, 1→完结（serialStatus）
    try:
        v = int(code)
    except (TypeError, ValueError):
        return ""
    return "连载" if v == 0 else "完结" if v == 1 else ""


def _hit_from_search_item(d: dict) -> ScrapeHit:
    bid = str(d.get("bookId") or "")
    if not bid:
        return ScrapeHit()
    name = _strip_font(str(d.get("name") or ""))
    author = _clean(str(d.get("authorName") or ""))
    cover = str(d.get("coverUrlNonLogo") or d.get("coverUrl") or "")
    if cover.startswith("//"):
        cover = "https:" + cover
    elif cover.startswith("/"):
        cover = "https://static.zongheng.com" + cover
    keywords = str(d.get("keyword") or "")
    tags = [clean_tag_token(t) for t in re.split(r"[,，、|]", keywords)]
    tags = [t for t in tags if t]
    cat = _clean(str(d.get("catePName") or d.get("cateFineName") or ""))
    intro = _clean(str(d.get("description") or ""))[:500]
    latest = _clean(str(d.get("chapterName") or ""))
    try:
        word_count = int(d.get("totalWord") or 0)
    except (TypeError, ValueError):
        word_count = 0
    return ScrapeHit(
        source=SOURCE_NAME,
        source_id=bid,
        name=name,
        author=author,
        latest_chapter=latest,
        cover_url=cover or cover_url_for(bid),
        url=book_url_for(bid),
        intro=intro,
        status=_status_from_serial(d.get("serialStatus")),
        category=map_category(cat),
        word_count=word_count,
        tags=tags[:8],
    )


def search(keyword: str, limit: int = 10, enrich: bool = True) -> list[ScrapeHit]:
    """搜书。enrich 仅与其它源接口对齐（搜索 JSON 已含较全字段，不额外拉详情）。"""
    keyword = (keyword or "").strip()
    if not keyword:
        raise ScrapeError("请填写搜索关键词")
    keyword = re.sub(r"[《》〈〉]", "", keyword)
    keyword = re.sub(r"作者\s*[：:]\s*\S+\s*$", "", keyword).strip() or keyword

    qs = urllib.parse.urlencode(
        {
            "keyword": keyword,
            "sort": "null",
            "pageNo": "1",
            "pageNum": str(max(1, min(limit, 20))),
            "isFromHuayu": "0",
        }
    )
    text = _http_get(f"{_SEARCH_API}?{qs}", headers={"Accept": "application/json"})
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ScrapeError(f"纵横搜索响应不是 JSON: {e}") from e

    if data.get("code") not in (0, "0", None):
        raise ScrapeError(f"纵横搜索错误: code={data.get('code')}")

    lst = (((data or {}).get("data") or {}).get("datas") or {}).get("list") or []
    hits = [_hit_from_search_item(x) for x in lst if x.get("bookId")]
    return hits[:limit]


def fetch_detail(book_id: str) -> ScrapeHit:
    book_id = (book_id or "").strip()
    if not re.fullmatch(r"\d{5,16}", book_id):
        raise ScrapeError("无效的纵横 bookId")

    page = _http_get(book_url_for(book_id))
    if len(page) < 500:
        raise ScrapeError("无法获取纵横详情")

    hit = ScrapeHit(
        source=SOURCE_NAME,
        source_id=book_id,
        url=book_url_for(book_id),
        cover_url="",
    )

    def meta(*keys: str) -> str:
        for key in keys:
            m = re.search(
                r'<meta[^>]+(?:name|property)=["\']' + re.escape(key) + r'["\'][^>]+content=["\']([^"\']*)["\']',
                page,
                re.I,
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\']' + re.escape(key) + r'["\']',
                page,
                re.I,
            )
            if m:
                return _clean(html_lib.unescape(m.group(1)))
        return ""

    title = meta("og:novel:book_name", "og:title")
    if title:
        hit.name = re.sub(r"[_|-].{0,40}纵横.*$", "", title).strip() or title
    if not hit.name:
        m = re.search(r"<title>([^<_—|-]+)", page)
        if m:
            hit.name = _clean(m.group(1))

    hit.author = meta("og:novel:author")
    if not hit.author:
        # SSR：author-info--name 区块
        m = re.search(r'class="author-info--name"[^>]*>[\s\S]*?<a[^>]*>\s*([^<]+)', page)
        if m:
            hit.author = _clean(m.group(1))

    cover = meta("og:image")
    if cover.startswith("//"):
        cover = "https:" + cover
    hit.cover_url = cover

    # —— 分类：只认 og / 顶栏细分类（de-tags 是风格标签，绝不能当分类）——
    cat = meta("og:novel:category")
    if not cat:
        m = re.search(r'class="[^"]*de-header-line[^"]*"[\s\S]{0,300}?<span[^>]*>\s*([^<]{1,16})\s*</span>', page)
        if m:
            cat = _clean(m.group(1))
    if not cat:
        m = re.search(r'class="cateFineId"[^>]*>\s*([^<]+)', page)
        if m:
            cat = _clean(m.group(1))
    hit.category = map_category(cat)

    status_raw = meta("og:novel:status")
    if "完结" in status_raw or "完本" in status_raw:
        hit.status = "完结"
    elif "连载" in status_raw:
        hit.status = "连载"
    else:
        m = re.search(r'class="serialStatus"[^>]*>\s*([^<]+)', page)
        if m:
            s = _clean(m.group(1))
            if "完结" in s or "完本" in s:
                hit.status = "完结"
            elif "连载" in s:
                hit.status = "连载"

    # —— 简介：优先 JbookSummary（真实简介），SEO meta 仅作最后兜底 ——
    intro = ""
    m = re.search(
        r'class="[^"]*JbookSummary[^"]*"\s*>\s*<textarea[^>]*>([\s\S]*?)</textarea>',
        page,
    )
    if not m:
        m = re.search(
            r'class="[^"]*JbookSummary[^"]*"\s*>\s*<span[^>]*>([\s\S]*?)</span>',
            page,
        )
    if m:
        intro = _clean(m.group(1))
    if not intro or _is_seo_intro(intro):
        raw = meta("og:novel:introduction")
        if raw and not _is_seo_intro(raw):
            intro = _clean(raw)
    if not intro or _is_seo_intro(intro):
        raw = meta("og:description", "description")
        if raw and not _is_seo_intro(raw):
            intro = _clean(raw)
        elif raw and not intro:
            # 仍无简介时保留 SEO 文案，避免空简介
            intro = _clean(raw)
    hit.intro = intro[:500]

    latest = meta("og:novel:latest_chapter_name")
    if not latest:
        m = re.search(r'class="book-info--chapter-name[^"]*"[^>]*>[\s\S]*?title="[^"]*"\s*[^>]*>\s*([^<]+)', page)
        if m:
            latest = _clean(m.group(1))
    hit.latest_chapter = latest

    # —— 标签：优先 de-tags；去掉栏目名/垃圾词，禁用 keywords SEO ——
    tags: list[str] = []
    m = re.search(r'class="[^"]*de-tags[^"]*"[\s\S]{0,600}', page)
    if m:
        for t in re.findall(r"<span[^>]*>\s*([^<]{1,16})\s*</span>", m.group(0)):
            tok = clean_tag_token(_clean(t))
            if tok and not _is_junk_tag(tok, hit.name) and tok not in tags:
                tags.append(tok)
    if not tags:
        m = re.search(r'class="serialStatus"[^>]*>[\s\S]{0,800}?</div>', page)
        if m:
            for t in re.findall(r"<span[^>]*>\s*([^<]{1,16})\s*</span>", m.group(0)):
                tok = clean_tag_token(_clean(t))
                if tok and not _is_junk_tag(tok, hit.name) and tok not in tags:
                    tags.append(tok)
    hit.tags = tags[:8]

    # 字数：「97.7万字」/「1234字」
    m = re.search(r'([\d.]+)\s*万字(?:数)?', page)
    if m:
        try:
            hit.word_count = int(float(m.group(1)) * 10000)
        except ValueError:
            pass
    else:
        m = re.search(r'(\d{2,9})\s*字', page)
        if m:
            try:
                hit.word_count = int(m.group(1))
            except ValueError:
                pass

    return hit


def download_cover(url: str, dest) -> str:
    if not url:
        raise ScrapeError("没有封面地址")
    if url.startswith("//"):
        url = "https:" + url
    try:
        data, ctype = http_get_bytes(
            url, headers={"Referer": "https://www.zongheng.com/"}, timeout=TIMEOUT
        )
    except HttpError as exc:
        raise ScrapeError(f"封面下载失败: {exc}") from exc
    if "png" in ctype:
        ext = ".png"
    elif "webp" in ctype:
        ext = ".webp"
    elif "gif" in ctype:
        ext = ".gif"
    else:
        ext = ".jpg"
    dest.write_bytes(data)
    return ext
