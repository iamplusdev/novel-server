"""番茄小说刮削（标准库）。

搜索: https://fanqienovel.com/api/author/search/search_book/v1?query_word=
详情: https://fanqienovel.com/page/{book_id}
"""
from __future__ import annotations

import gzip
import html as html_lib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .qidian import ScrapeError, ScrapeHit, clean_tag_token

SOURCE_NAME = "番茄"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 20
_SEARCH_API = "https://fanqienovel.com/api/author/search/search_book/v1"


def _http_get(url: str, headers: dict | None = None) -> str:
    hdrs = {
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": "https://fanqienovel.com/",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        raise ScrapeError(f"番茄请求失败 HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ScrapeError(f"番茄连接失败: {e.reason}") from e


def _clean(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def cover_url_for(book_id: str) -> str:
    return f"https://fanqienovel.com/page/{book_id}"  # 无稳定直链时用详情页，有 thumb_url 则覆盖


def book_url_for(book_id: str) -> str:
    return f"https://fanqienovel.com/page/{book_id}"


def _status_from_code(code) -> str:
    # 捕获样本: 0→完本(目录含完本感言), 1→连载
    try:
        v = int(code)
    except (TypeError, ValueError):
        return ""
    return "完结" if v == 0 else "连载" if v == 1 else ""


def _hit_from_search_item(d: dict) -> ScrapeHit:
    bid = str(d.get("book_id") or "")
    tags = []
    cat_main = ""
    for part in re.split(r"[,，\s]+", str(d.get("category") or "")):
        tag = clean_tag_token(part)
        if not tag:
            continue
        if not cat_main:
            cat_main = tag
        if tag not in tags:
            tags.append(tag)
    return ScrapeHit(
        source=SOURCE_NAME,
        source_id=bid,
        name=_clean(d.get("book_name") or ""),
        author=_clean(d.get("author") or ""),
        latest_chapter=_clean(d.get("last_chapter_title") or ""),
        cover_url=_clean(d.get("thumb_url") or ""),
        url=book_url_for(bid),
        intro=_clean(d.get("book_abstract") or "")[:300],
        status=_status_from_code(d.get("creation_status")),
        category=cat_main,
        word_count=int(d.get("word_count") or 0),
        tags=tags[:8],
    )


def search(keyword: str, limit: int = 10) -> list[ScrapeHit]:
    keyword = (keyword or "").strip()
    if not keyword:
        raise ScrapeError("请填写搜索关键词")
    keyword = re.sub(r"[《》〈〉]", "", keyword)
    keyword = re.sub(r"[（(][^）)]*?(?:校对|精校|全本|修订)[^）)]*[）)]", "", keyword).strip()
    keyword = re.sub(r"作者\s*[：:]\s*\S+\s*$", "", keyword).strip() or (keyword or "").strip()

    qs = urllib.parse.urlencode(
        {
            "filter": "127,127,127,127",
            "page_count": str(max(1, min(limit, 20))),
            "page_index": "0",
            "query_type": "0",
            "query_word": keyword,
        }
    )
    # 先不带反爬参数请求；失败再带空 msToken
    last_err: Exception | None = None
    data = None
    for url in (
        f"{_SEARCH_API}?{qs}",
        f"{_SEARCH_API}?{qs}&msToken=",
    ):
        try:
            text = _http_get(url, headers={"Accept": "application/json"})
            data = json.loads(text)
            break
        except (ScrapeError, json.JSONDecodeError) as e:
            last_err = e
    if data is None:
        raise ScrapeError(str(last_err) if last_err else "番茄搜索失败")

    if data.get("code") not in (0, "0", None):
        raise ScrapeError(f"番茄搜索错误: code={data.get('code')}")

    items = (((data or {}).get("data") or {}).get("search_book_data_list")) or []
    hits = [_hit_from_search_item(x) for x in items if x.get("book_id")]
    if not hits and not items:
        raise ScrapeError(
            "番茄搜索接口返回空（需 a_bogus/msToken 签名）。"
            "可改用书号/详情链接刮削，例如 7276384138653862966"
        )
    return hits[:limit]


def extract_book_id(text: str) -> str:
    s = (text or "").strip()
    m = re.search(r"fanqienovel\.com/page/(\d{5,24})", s)
    if m:
        return m.group(1)
    m = re.search(r"(\d{5,24})", s)
    return m.group(1) if m else ""


def fetch_detail(book_id: str) -> ScrapeHit:
    book_id = (book_id or "").strip()
    if not re.fullmatch(r"\d{5,24}", book_id):
        raise ScrapeError("无效的番茄 bookId")
    page = _http_get(book_url_for(book_id))
    hit = ScrapeHit(source=SOURCE_NAME, source_id=book_id, url=book_url_for(book_id))

    # JSON-LD
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>([\s\S]*?)</script>', page
    ):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("headline") and not hit.name:
            t = _clean(str(obj.get("headline")))
            t = re.sub(r"完整版在线免费阅读.*$", "", t)
            t = re.sub(r"[_|-].{0,40}番茄小说.*$", "", t)
            hit.name = t.strip() or hit.name
        authors = obj.get("author")
        if isinstance(authors, list) and authors and not hit.author:
            a = authors[0]
            if isinstance(a, dict):
                hit.author = _clean(a.get("name") or "")
            else:
                hit.author = _clean(str(a))
        imgs = obj.get("image")
        if isinstance(imgs, list) and imgs and not hit.cover_url:
            hit.cover_url = str(imgs[0])
        elif isinstance(imgs, str) and imgs and not hit.cover_url:
            hit.cover_url = imgs

    # __INITIAL_STATE__.page
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]*?\});?\s*(?:function|</script>|$)", page)
    if m:
        raw_json = m.group(1)
        # 尽力截取到 page 段
        try:
            state = json.loads(raw_json)
        except json.JSONDecodeError:
            # 太长/含函数时，用正则抽字段
            state = None
            for key, pat in (
                ("author", r'"author"\s*:\s*"([^"]+)"'),
                ("bookName", r'"bookName"\s*:\s*"([^"]+)"'),
                ("status", r'"status"\s*:\s*(\d+)'),
                ("abstract", r'"abstract"\s*:\s*"([^"]*)"'),
                ("thumb", r'"thumb_url"\s*:\s*"([^"]+)"'),
                ("category", r'"category"\s*:\s*"([^"]*)"'),
            ):
                mm = re.search(pat, raw_json)
                if not mm:
                    continue
                if key == "author" and not hit.author:
                    hit.author = _clean(mm.group(1))
                elif key == "bookName" and not hit.name:
                    hit.name = _clean(mm.group(1))
                elif key == "status":
                    hit.status = _status_from_code(mm.group(1)) or hit.status
                elif key == "abstract" and not hit.intro:
                    hit.intro = _clean(json.loads('"'+mm.group(1)+'"') if False else mm.group(1))[:500]
                elif key == "thumb" and not hit.cover_url:
                    u = mm.group(1).encode().decode("unicode_escape") if "\\u" in mm.group(1) else mm.group(1)
                    hit.cover_url = u
                elif key == "category" and not hit.category:
                    hit.category = _clean(mm.group(1))
        if isinstance(state, dict):
            page_st = state.get("page") or {}
            if not hit.author:
                hit.author = _clean(page_st.get("author") or "")
            if not hit.name:
                hit.name = _clean(page_st.get("bookName") or "")
            if not hit.status:
                hit.status = _status_from_code(page_st.get("status"))
            if not hit.intro:
                hit.intro = _clean(page_st.get("abstract") or "")[:500]
            cat2 = page_st.get("categoryV2") or page_st.get("category") or ""
            if cat2 and not hit.category:
                names = re.findall(r'"Name"\s*:\s*"([^"]+)"', cat2 if isinstance(cat2, str) else "")
                if names:
                    hit.category = names[0]
                    hit.tags = [clean_tag_token(x) for x in names if clean_tag_token(x)][:8]

    # 简介：目录前正文段 / abstract / meta description
    if not hit.intro:
        m = re.search(
            r'class="[^"]*(?:page-abstract|book-abstract|abstract|book-info)[^"]*"[^>]*>([\s\S]{10,800}?)</(?:p|div)>',
            page,
        )
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(r'>([^<]{20,400})</p></div><div class="page-directory-header"', page)
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(r'"abstract"\s*:\s*"([^"]{10,500})"', page)
        if m:
            try:
                raw = bytes(m.group(1), "utf-8").decode("unicode_escape")
            except Exception:
                raw = m.group(1)
            hit.intro = _clean(raw)[:500]
    if not hit.intro:
        m = re.search(r'<meta name="description" content="([^"]+)"', page)
        if m:
            hit.intro = _clean(m.group(1))[:500]

    # 目录最后章节标题
    chapters = re.findall(
        r'class="chapter-item-title"[^>]*>\s*([^<]{1,80})\s*<', page
    )
    if chapters and not hit.latest_chapter:
        hit.latest_chapter = _clean(chapters[-1])

    if not hit.status:
        m = re.search(r'"status"\s*:\s*(\d+)', page)
        if m:
            hit.status = _status_from_code(m.group(1))
    if not hit.tags and hit.category:
        hit.tags = [clean_tag_token(x) for x in re.split(r"[,，]", hit.category) if clean_tag_token(x)]
    return hit


def download_cover(url: str, dest) -> str:
    if not url:
        raise ScrapeError("没有封面地址")
    if url.startswith("//"):
        url = "https:" + url
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://fanqienovel.com/"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
    except Exception as exc:  # noqa: BLE001
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
