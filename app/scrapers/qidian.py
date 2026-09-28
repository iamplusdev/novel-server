"""起点中文网刮削（标准库 HTML 解析，仅元数据，不抓正文）。

优先使用移动端搜索（较不易被 WAF 拦）：
  搜索 https://m.qidian.com/search?kw={关键词}
  详情 https://www.qidian.com/book/{bookId}/  （失败则回退搜索结果字段）
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from dataclasses import dataclass, field

from .http_util import HttpError, http_get, http_get_bytes

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1 "
    "QDReader/7.9.38"
)
TIMEOUT = 20
SOURCE_NAME = "起点"


class ScrapeError(Exception):
    """刮削失败。blocked=True 表示疑似被站点风控/限流拦截。"""

    blocked = False


class RateLimitedError(ScrapeError):
    """被起点 WAF/验证码探针拦截，应退避等待而不是继续猛刷。"""

    blocked = True


# 风控/验证探针页特征（响应头/正文里常见）
_BLOCK_MARKERS = (
    "probe.js",
    "probev3.js",
    "TCaptcha",
    "turing.captcha",
    "x-waf-captcha",
    "安全验证",
    "环境异常",
    "请完成验证",
)


def looks_blocked(page: str | None) -> bool:
    """判断是否为风控/验证探针页（而非正常书目 HTML）。"""
    if not page:
        return False
    head = page[:3000]
    return any(m in head for m in _BLOCK_MARKERS)


@dataclass
class ScrapeHit:
    source: str = SOURCE_NAME
    source_id: str = ""
    name: str = ""
    author: str = ""
    latest_chapter: str = ""
    cover_url: str = ""
    url: str = ""
    intro: str = ""
    status: str = ""
    category: str = ""
    word_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "name": self.name,
            "author": self.author,
            "latest_chapter": self.latest_chapter,
            "cover_url": self.cover_url,
            "url": self.url,
            "intro": self.intro,
            "status": self.status,
            "category": self.category,
            "word_count": self.word_count,
            "tags": self.tags,
        }


def extract_detail_tags(page: str) -> list[str]:
    """从详情页提取风格标签。

    PC: p.all-label > a（/all/tagXXX/）
    移动: ul.tags > li.tag > a（/category/tags/XXX/）
    """
    tags: list[str] = []

    def _add(t: str) -> None:
        tok = clean_tag_token(t)
        if tok and tok not in tags and tok not in ("相似标签小说", "排行榜"):
            tags.append(tok)

    # 1) PC all-label
    label_html = ""
    m = re.search(
        r'class=["\'][^"\']*all-label[^"\']*["\'][^>]*>([\s\S]*?)</p>', page
    )
    if m:
        label_html = m.group(1)
    elif "all-label" in page:
        i = page.find("all-label")
        label_html = page[i : i + 900]
    if label_html:
        for t in re.findall(r"<a[^>]*>\s*([^<]{1,12}?)\s*</a>", label_html):
            _add(t)

    # 2) 移动端 ul.tags > li.tag
    if not tags:
        m = re.search(
            r'<ul class="tags"[^>]*>([\s\S]*?)</ul>', page
        )
        zone = m.group(1) if m else ""
        if not zone:
            # 宽松：取第一组 li.tag
            m = re.search(
                r'(<li class="tag"[\s\S]*?</li>\s*){2,}', page
            )
            zone = m.group(0) if m else ""
        if zone:
            for href, text in re.findall(
                r'<a href="([^"]*(?:/all/tag|/category/tags)/[^"]*)"[^>]*>\s*([^<]{1,12}?)\s*</a>',
                zone,
            ):
                _add(text)
                if not clean_tag_token(text):
                    _add(urllib.parse.unquote(re.sub(r".*/(?:all/tag|category/tags)/", "", href).strip("/")))

    # 3) 全页 /all/tagXXX/ 或 /category/tags/XXX/
    if not tags:
        seen = set()
        for raw in re.findall(r"/(?:all/tag|category/tags)/([^/\"'?#]+)/", page):
            tok = clean_tag_token(urllib.parse.unquote(raw))
            if tok and tok not in seen and " " not in tok and "+" not in tok:
                seen.add(tok)
                tags.append(tok)
    return tags[:8]


def _http_get(url: str) -> str:
    """统一走 http_util：默认直连，避免本地代理未启动导致批量失败。

    移动端页面固定使用阅读器/手机 UA，与 m.qidian.com 访问形态一致。
    """
    try:
        return http_get(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Referer": "https://m.qidian.com/",
            },
            timeout=TIMEOUT,
        )
    except HttpError as e:
        # 保留「起点」语义，便于批处理日志识别
        raise ScrapeError(f"起点{e}") from e


def _clean(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_keyword(keyword: str) -> str:
    keyword = (keyword or "").strip()
    keyword = re.sub(r"[（(].{0,30}?(著|作品|文|校对版全本)[）)]", "", keyword)
    keyword = re.sub(r"《|》|〈|〉", "", keyword)
    keyword = re.sub(r"\(校对版全本\)|（校对版全本）", "", keyword)
    keyword = re.sub(r"^《?作者[：:][^》]+》?", "", keyword)
    return keyword.strip()[:40]


STATUS_WORDS = {"连载", "完结", "太监", "断更", "连载中", "已完结", "完本", "新书"}
WORD_RE = re.compile(r"^[\d.]+\s*(万|亿)?\s*字?$")
# 常见频道/分类，应写入 category 而不是 tags
CATEGORY_WORDS = {
    "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史",
    "游戏", "体育", "科幻", "诸天无限", "悬疑灵异", "轻小说", "短篇",
    "女频", "男频", "言情", "古代", "现代", "未来", "玄幻奇幻",
}
# 明显不是标签的噪声
NOISE_TAGS = {
    "起点", "中文网", "免费", "vip", "VIP", "签约", "精品", "热门",
    "推荐", "收藏", "点击", "排行", "完本", "全本", "校对版全本",
}


def is_status_token(t: str) -> bool:
    return t in STATUS_WORDS


def is_wordcount_token(t: str) -> bool:
    return bool(WORD_RE.match(t))


def is_category_token(t: str) -> bool:
    return t in CATEGORY_WORDS


def clean_tag_token(t: str) -> str:
    t = _clean(t)
    if not t or len(t) > 12:
        return ""
    if t in NOISE_TAGS or is_status_token(t) or is_wordcount_token(t):
        return ""
    if is_category_token(t):
        return ""
    # 纯数字 / 字数
    if re.fullmatch(r"[\d.]+", t):
        return ""
    return t


def classify_tip_token(t: str) -> tuple[str, str]:
    """返回 (kind, value)，kind in category|status|word_count|tag|skip"""
    t = _clean(t)
    if not t:
        return "skip", ""
    if is_status_token(t):
        if t in ("完结", "已完结", "完本", "全本"):
            return "status", "完结"
        if t in ("连载", "连载中"):
            return "status", "连载"
        return "status", "未知"
    if is_wordcount_token(t):
        m = re.match(r"([\d.]+)\s*(万|亿)?", t)
        if m:
            num = float(m.group(1))
            unit = m.group(2) or ""
            n = int(num * (10000 if unit == "万" else 100000000 if unit == "亿" else 1))
            return "word_count", str(n)
        return "skip", ""
    if is_category_token(t):
        return "category", t
    tag = clean_tag_token(t)
    if tag:
        return "tag", tag
    return "skip", ""


def cover_url_for(book_id: str) -> str:
    return f"https://bookcover.yuewen.com/qdbimg/349573/{book_id}/180.webp"


def book_url_for(book_id: str) -> str:
    return f"https://www.qidian.com/book/{book_id}/"

def extract_book_id(text: str) -> str:
    """从 URL 或纯数字提取起点 bookId。"""
    s = (text or "").strip()
    m = re.search(r"qidian\.com/(?:book|info)/(\d{5,12})", s)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\d{5,12})", s)
    return m.group(1) if m else ""



def _parse_mobile_search(page: str, limit: int) -> list[ScrapeHit]:
    hits: list[ScrapeHit] = []
    # 按 y-list__item 切块（class 名带 hash，故用宽松匹配）
    blocks = re.split(r'<div class="y-list__item"', page)
    for block in blocks[1:]:
        m_id = re.search(r'data-bid="(\d+)"', block)
        if not m_id:
            continue
        bid = m_id.group(1)
        name = ""
        m_name = re.search(
            r'class="[^"]*_searchBookName[^"]*"[^>]*>([\s\S]*?)</h2>', block
        )
        if m_name:
            name = _clean(re.sub(r"</?mark>", "", m_name.group(1)))
        if not name:
            m_name = re.search(r'title="([^"]+?)在线阅读"', block)
            if m_name:
                name = _clean(m_name.group(1))
        if not name:
            continue

        author = ""
        m_a = re.search(
            r'class="[^"]*_searchBookAuthor[^"]*"[^>]*>\s*([^<]+)', block
        )
        if m_a:
            author = _clean(m_a.group(1))

        intro = ""
        m_d = re.search(
            r'class="[^"]*_searchBookDesc[^"]*"[^>]*>([\s\S]*?)</p>', block
        )
        if m_d:
            intro = _clean(m_d.group(1))[:300]

        status = ""
        category = ""
        word_count = 0
        tags = []
        # 书目角标：分类 / 状态 / 字数；其余才是标签
        tip_block = ""
        m_tips = re.search(
            r'class="[^"]*_tags[^"]*"[^>]*>([\s\S]*?)</div>', block
        ) or re.search(r'class="[^"]*_bookTips[^"]*"[^>]*>([\s\S]*?)</div></div>', block)
        if m_tips:
            tip_block = m_tips.group(1)
        tokens = re.findall(r"<p>([^<]{1,16})</p>", tip_block) if tip_block else []
        if not tokens:
            tokens = re.findall(r"<p>([^<]{1,16})</p>", block)
        for t in tokens:
            kind, val = classify_tip_token(t)
            if kind == "status" and val:
                status = val
            elif kind == "category" and val and not category:
                category = val
            elif kind == "word_count" and val.isdigit():
                word_count = int(val)
            elif kind == "tag" and val and val not in tags:
                tags.append(val)

        cover = ""
        m_img = re.search(r'data-src="([^"]+)"', block) or re.search(r'src="([^"]*qdbimg[^"]*)"', block)
        if m_img:
            cover = m_img.group(1)
            if cover.startswith("//"):
                cover = "https:" + cover
        if not cover:
            cover = cover_url_for(bid)

        hits.append(
            ScrapeHit(
                source_id=bid,
                name=name,
                author=author,
                intro=intro,
                status=status,
                category=category,
                word_count=word_count,
                tags=tags[:6],
                cover_url=cover,
                url=book_url_for(bid),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _parse_pc_search(page: str, limit: int) -> list[ScrapeHit]:
    hits: list[ScrapeHit] = []
    seen: set[str] = set()
    blocks = re.findall(
        r'<div class="book-wrap-new"[\s\S]*?(?=<div class="book-wrap-new"|<div class="j_my_fans"|</body>)',
        page,
    )
    for block in blocks:
        m_id = re.search(r'data-(?:bid|bookid)="(\d+)"', block)
        if not m_id:
            continue
        bid = m_id.group(1)
        if bid in seen:
            continue
        m_title = re.search(
            r'<h4>\s*<a[^>]*data-bid="%s"[^>]*>\s*([^<]+?)\s*</a>' % bid, block
        ) or re.search(r'<img[^>]+title="([^"]+)"', block)
        name = _clean(m_title.group(1) if m_title else "")
        if not name:
            continue
        author = ""
        m_author = re.search(r'class="[^"]*author[^"]*"[^>]*>\s*(?:<a[^>]*>)?\s*([^<]+)', block)
        if m_author:
            author = _clean(m_author.group(1))
        hits.append(
            ScrapeHit(
                source_id=bid,
                name=name,
                author=author,
                cover_url=cover_url_for(bid),
                url=book_url_for(bid),
            )
        )
        seen.add(bid)
        if len(hits) >= limit:
            break
    return hits


def search(keyword: str, limit: int = 10, enrich: bool = True) -> list[ScrapeHit]:
    """搜书。enrich=True 时会给部分结果补详情（请求多，手动刮削用）；批量请传 False。"""
    keyword = _norm_keyword(keyword)
    if not keyword:
        raise ScrapeError("请填写搜索关键词")
    enc = urllib.parse.quote(keyword)

    page = _http_get(f"https://m.qidian.com/search?kw={enc}")
    # 搜索页本身被风控且无结果时，明确报拦截，便于上层退避
    if looks_blocked(page) and "data-bid" not in page:
        raise RateLimitedError("起点搜索触发风控拦截，请稍后再试")
    hits = _parse_mobile_search(page, limit)
    if not hits and ("probe" not in page and "data-bid" not in page):
        # 回退 PC 搜索
        page = _http_get(f"https://www.qidian.com/so/{enc}.html")
        if looks_blocked(page) and "data-bid" not in page:
            raise RateLimitedError("起点搜索触发风控拦截，请稍后再试")
        hits = _parse_pc_search(page, limit)
    if not hits:
        # PC 结构兜底扫 data-bid
        for bid, title in re.findall(r'data-bid="(\d+)"[^>]*>\s*([^<]{2,40})\s*</a>', page):
            name = _clean(title)
            if not name or name in ("加入书架",):
                continue
            hits.append(
                ScrapeHit(
                    source_id=bid,
                    name=name,
                    cover_url=cover_url_for(bid),
                    url=book_url_for(bid),
                )
            )
            if len(hits) >= limit:
                break

    # 补最新章节（详情页，最多 5 条）；批量刮削传 enrich=False 跳过，降低请求量
    if enrich:
        for h in hits[: min(5, len(hits))]:
            if h.latest_chapter and h.tags:
                continue
            try:
                detail = fetch_detail(h.source_id)
            except ScrapeError:
                continue
            h.latest_chapter = detail.latest_chapter or h.latest_chapter
            if not h.author:
                h.author = detail.author
            if not h.intro:
                h.intro = detail.intro[:300]
            if not h.status and detail.status:
                h.status = detail.status
            if not h.tags and detail.tags:
                h.tags = detail.tags
    return hits


def fetch_detail(book_id: str) -> ScrapeHit:
    book_id = (book_id or "").strip()
    if not re.fullmatch(r"\d{5,12}", book_id):
        raise ScrapeError("无效的起点 bookId")

    page = ""
    last_err: Exception | None = None
    for url in (book_url_for(book_id), f"https://m.qidian.com/book/{book_id}/"):
        try:
            page = _http_get(url)
            if len(page) > 3000 and not looks_blocked(page):
                break
        except ScrapeError as e:
            last_err = e
            page = ""
    if not page or (len(page) < 3000 and looks_blocked(page)):
        # 风控探针页再试一次 PC 详情
        try:
            page = _http_get(book_url_for(book_id))
        except ScrapeError as e:
            last_err = e
    if not page or len(page) < 500:
        if looks_blocked(page) or (last_err is not None and getattr(last_err, "blocked", False)):
            raise RateLimitedError("起点详情触发风控拦截，请稍后再试") from last_err
        raise ScrapeError(str(last_err) if last_err else "无法获取起点详情（可能被风控拦截）")

    hit = ScrapeHit(source_id=book_id, url=book_url_for(book_id), cover_url=cover_url_for(book_id))

    m = re.search(r"bookId\s*:\s*(\d+)", page)
    if m:
        hit.source_id = m.group(1)
    m = re.search(r"authorName\s*:\s*['\"]([^'\"]+)['\"]", page)
    if m:
        hit.author = _clean(m.group(1))
    if not hit.author:
        m = re.search(r'class="[^"]*_searchBookAuthor[^"]*"[^>]*>\s*([^<]+)', page)
        if m:
            hit.author = _clean(m.group(1))

    m = re.search(r"imgUrl\s*:\s*['\"]([^'\"]+)['\"]", page)
    if m:
        u = m.group(1).strip()
        hit.cover_url = "https:" + u if u.startswith("//") else u

    m = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page)
    if m:
        hit.name = _clean(m.group(1))
    if not hit.name:
        m = re.search(r"bookName\s*:\s*['\"]([^'\"]+)['\"]", page)
        if m:
            hit.name = _clean(m.group(1))
    if not hit.name:
        m = re.search(r"<title>([^<_—|-]+)", page)
        if m:
            hit.name = _clean(m.group(1))

    for pat in (
        r'id="book-intro"[^>]*>([\s\S]*?)</(?:p|div)>',
        r'class="book-intro[^"]*"[^>]*>([\s\S]*?)</(?:p|div)>',
        r'class="[^"]*_searchBookDesc[^"]*"[^>]*>([\s\S]*?)</p>',
        r'<meta name="description" content="([^"]+)"',
    ):
        m = re.search(pat, page)
        if m:
            hit.intro = _clean(m.group(1))[:500]
            if hit.intro:
                break

    if re.search(r"已完结|完本|>完结<", page):
        hit.status = "完结"
    elif re.search(r"连载中|>连载<", page):
        hit.status = "连载"

    m = re.search(r"channelName\s*:\s*['\"]([^'\"]+)['\"]", page)
    if m:
        ch = _clean(m.group(1))
        if ch and (is_category_token(ch) or len(ch) <= 6):
            hit.category = ch

    hit.tags = extract_detail_tags(page)

    m = re.search(r"最新章节[^<]*</[^>]+>\s*(?:<a[^>]*>)?\s*([^<]{2,80})", page)
    if m:
        hit.latest_chapter = _clean(m.group(1))
    if not hit.latest_chapter:
        chapters = re.findall(
            r'href="(?:https?:)?//(?:read|www|m)\.qidian\.com/chapter/[^"]+"[^>]*>\s*([^<]{2,80})\s*<',
            page,
        )
        if chapters:
            hit.latest_chapter = _clean(chapters[-1])
    if not hit.latest_chapter:
        m = re.search(r"latestChapterName\s*:\s*['\"]([^'\"]+)['\"]", page)
        if m:
            hit.latest_chapter = _clean(m.group(1))

    return hit


def download_cover(url: str, dest) -> str:
    if not url:
        raise ScrapeError("没有封面地址")
    if url.startswith("//"):
        url = "https:" + url
    try:
        data, ctype = http_get_bytes(
            url, headers={"Referer": "https://m.qidian.com/"}, timeout=TIMEOUT
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
