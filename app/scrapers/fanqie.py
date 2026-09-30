"""番茄小说刮削（标准库）。

搜索: https://fanqienovel.com/api/author/search/search_book/v1?query_word=
详情: https://fanqienovel.com/page/{book_id}
"""
from __future__ import annotations

import base64
import html as html_lib
import json
import re
import time
import urllib.parse

from ..config import STYLE_ONLY_TAGS, to_qidian_category
from .http_util import HttpError, http_get as _http_get_raw, http_get_bytes
from .qidian import ScrapeError, ScrapeHit, clean_tag_token

SOURCE_NAME = "番茄"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 20
_SEARCH_API = "https://fanqienovel.com/api/author/search/search_book/v1"

# 浏览器 warmup 结果缓存：TTL 内不重复打开番茄主页预热 Cookie，降低请求频率
_WARMUP_CACHE_TTL = 600.0  # 秒
_warmup_ok_until: float = 0.0


def map_category(raw: str) -> str:
    """番茄原栏目/标签 → 起点 15 类；风格标签/未知返回空串（由写库侧落未分类）。"""
    return to_qidian_category(raw)


def _http_get(url: str, headers: dict | None = None) -> str:
    """统一走 http_util：默认直连，避免本地代理未启动导致失败。"""
    try:
        return _http_get_raw(
            url,
            headers=headers or {"Referer": "https://fanqienovel.com/"},
            timeout=TIMEOUT,
            referer="https://fanqienovel.com/",
        )
    except HttpError as e:
        raise ScrapeError(f"番茄{e}") from e


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
    # 捕获样本: creationStatus/creation_status 0→完结, 1→连载
    try:
        v = int(code)
    except (TypeError, ValueError):
        return ""
    return "完结" if v == 0 else "连载" if v == 1 else ""


def _extract_initial_state(page: str) -> dict | None:
    """按花括号配平截取 window.__INITIAL_STATE__={...} 完整 JSON。

    页面收尾是 `}};` + `)()` + `</script>`，非贪婪正则会在首个 `}` 截断。
    """
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*\{", page)
    if not m:
        return None
    start = m.end() - 1  # 指向 '{'
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(page)):
        ch = page[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        state = json.loads(page[start : end + 1])
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) else None


def _names_from_category_v2(cat2) -> list[str]:
    """categoryV2 → 名称列表。

    详情页里是双重编码 JSON 字符串：`[{"Name":"都市高武","MainCategory":true},...]`，
    也可能是已解析的 list/dict。
    """
    items: list = []
    if isinstance(cat2, str) and cat2.strip():
        s = cat2.strip()
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = [parsed]
        else:
            # 兜底：从转义/未转义文本里抽 Name
            names = re.findall(r'\\"Name\\":\\"([^\\"]+)\\"', s) or re.findall(
                r'"Name"\s*:\s*"([^"]+)"', s
            )
            return [n for n in names if n]
    elif isinstance(cat2, list):
        items = cat2
    elif isinstance(cat2, dict):
        items = [cat2]

    names: list[str] = []
    main_first: list[str] = []
    other: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = _clean(str(it.get("Name") or it.get("name") or ""))
        if not name:
            continue
        if it.get("MainCategory") is True or it.get("main_category") is True:
            main_first.append(name)
        else:
            other.append(name)
    # 主分类在前，便于 map_category 取第一个
    names = main_first + other
    return names


def _category_from_names(names: list[str]) -> str:
    """名称列表 → 起点标准分类；风格标签跳过。"""
    for n in names:
        if not n or n in STYLE_ONLY_TAGS:
            continue
        mapped = map_category(n)
        if mapped:
            return mapped
    return ""


def _hit_from_search_item(d: dict) -> ScrapeHit:
    bid = str(d.get("book_id") or "")
    tags = []
    cat_main = ""
    for part in re.split(r"[,，\s]+", str(d.get("category") or "")):
        tag = clean_tag_token(part)
        if not tag:
            continue
        # 风格标签（第一人称/开局等）只进 tags，不参与选主分类
        if not cat_main and tag not in STYLE_ONLY_TAGS:
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
        category=map_category(cat_main),
        word_count=int(d.get("word_count") or 0),
        tags=tags[:8],
    )


# 必应反查：单次书名最多取几个候选书号
_BING_MAX_IDS = 3


def _bing_fanqie_ids(keyword: str) -> list[str]:
    """用 cn.bing.com 反查番茄书号：「书名 site:fanqienovel.com/page」。

    解析结果页里的 fanqienovel.com/page/{id}；兼容 Bing ck/a 跳转里的 base64 原链。
    失败返回 []，不抛异常。
    """
    q = urllib.parse.quote(f"{keyword} site:fanqienovel.com/page")
    url = f"https://cn.bing.com/search?q={q}&count=10"
    try:
        page = _http_get_raw(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=TIMEOUT,
            referer="https://cn.bing.com/",
        )
    except (HttpError, ScrapeError):
        return []
    if not page or len(page) < 200:
        return []

    found: list[str] = []

    def _add(bid: str) -> None:
        if bid and bid not in found:
            found.append(bid)

    # 1) 直接链接：fanqienovel.com/page/{id}
    for bid in re.findall(r"fanqienovel\.com/page/(\d{5,24})", page):
        _add(bid)
        if len(found) >= _BING_MAX_IDS:
            return found[:_BING_MAX_IDS]

    # 2) Bing 跳转包装：/ck/a?...&u=a1<base64>...
    for m in re.finditer(r"[?&]u=a1([A-Za-z0-9_\-]+)", page):
        raw = m.group(1)
        try:
            pad = raw + "=" * (-len(raw) % 4)
            decoded = base64.urlsafe_b64decode(pad).decode("utf-8", "ignore")
        except (ValueError, OSError):
            continue
        for bid in re.findall(r"fanqienovel\.com/page/(\d{5,24})", decoded):
            _add(bid)
            if len(found) >= _BING_MAX_IDS:
                return found[:_BING_MAX_IDS]
    return found[:_BING_MAX_IDS]


def _search_via_bing(keyword: str, limit: int) -> list[ScrapeHit]:
    """官方搜索 API 不可用时：必应反查书号 → fetch_detail 组装结果。"""
    ids = _bing_fanqie_ids(keyword)
    if not ids:
        return []
    hits: list[ScrapeHit] = []
    for bid in ids[:_BING_MAX_IDS]:
        try:
            hits.append(fetch_detail(bid))
        except ScrapeError:
            continue
        if len(hits) >= limit:
            break
    return hits[:limit]


def search(keyword: str, limit: int = 10, enrich: bool = True) -> list[ScrapeHit]:
    """搜书。enrich 仅与起点接口对齐（番茄搜索不额外拉详情），保持调用方统一。"""
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
    # 先不带反爬参数请求；失败再带空 msToken / 去掉 filter，尽量提高成功率
    data = None
    qs_nofilter = urllib.parse.urlencode(
        {
            "page_count": str(max(1, min(limit, 20))),
            "page_index": "0",
            "query_type": "0",
            "query_word": keyword,
        }
    )

    # 浏览器模式：先打开番茄主页预热 Cookie（msToken 等），并跳过空 msToken 变体
    # （预热后 Cookie 里可能已有真实 msToken，query 上再挂空值反而易失败）
    browser_on = False
    try:
        from .http_util import browser_mode

        browser_on = browser_mode()
    except Exception:  # noqa: BLE001
        browser_on = False
    if browser_on:
        global _warmup_ok_until
        # warmup 结果短缓存：成功预热后 10 分钟内不再重复打开主页
        if time.time() >= _warmup_ok_until:
            try:
                from .browser_fallback import warmup

                if warmup("https://fanqienovel.com/"):
                    _warmup_ok_until = time.time() + _WARMUP_CACHE_TTL
            except Exception:  # noqa: BLE001
                pass

    # 书名搜索 API 需 a_bogus/msToken 签名，API/Chrome 均不稳定：
    # 只试 1 个变体；失败后用必应反查书号，再不行才报错
    try_urls = (f"{_SEARCH_API}?{qs_nofilter}",)
    api_err: str = ""
    for url in try_urls:
        try:
            text = _http_get(url, headers={"Accept": "application/json"})
        except ScrapeError as e:
            api_err = str(e)
            continue
        body = (text or "").strip()
        if not body:
            # 空 body：常见于未签名被拦或空响应
            api_err = "搜索接口空响应（未签名或被拦截）"
            continue
        if body.startswith("<"):
            # HTML 拦截页/降级页，不是 JSON
            api_err = "搜索接口返回 HTML 拦截页（需 a_bogus 签名）"
            continue
        try:
            data = json.loads(body)
            break
        except json.JSONDecodeError:
            # 避免把「Expecting value...」裸抛给用户
            api_err = "搜索接口非 JSON 响应（签名失败或内容被篡改）"
            continue

    if data is None:
        # 降级：cn.bing.com 反查 fanqienovel.com/page/{id}，再走稳定详情
        hits = _search_via_bing(keyword, limit=limit)
        if hits:
            return hits
        raise ScrapeError(
            f"番茄书名搜索失败: {api_err or '无响应'}。"
            "必应反查也未找到书号。请改用书号或详情链接刮削，"
            "例如 7276384138653862966 或 https://fanqienovel.com/page/7276384138653862966"
        )

    if data.get("code") not in (0, "0", None):
        hits = _search_via_bing(keyword, limit=limit)
        if hits:
            return hits
        raise ScrapeError(
            f"番茄书名搜索错误: code={data.get('code')}。"
            "必应反查也未找到书号。请改用书号或详情链接刮削（书名搜索需签名，不可靠）"
        )

    items = (((data or {}).get("data") or {}).get("search_book_data_list")) or []
    hits = [_hit_from_search_item(x) for x in items if x.get("book_id")]
    if not hits and not items:
        # 搜索接口可能要求 a_bogus/msToken 签名；必应反查 + 书号/链接仍可用
        hits = _search_via_bing(keyword, limit=limit)
        if hits:
            return hits
        raise ScrapeError(
            "番茄书名搜索返回空（需 a_bogus/msToken 签名，API/Chrome 均不好用）。"
            "必应反查也未找到书号。请改用书号或详情链接刮削，例如 7276384138653862966 "
            "或 https://fanqienovel.com/page/7276384138653862966"
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

    # __INITIAL_STATE__.page（括号配平截取，失败则正则兜底）
    state = _extract_initial_state(page)
    raw_json = ""
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*\{", page)
    if m:
        # 正则兜底用的原始片段（尽量多取）
        m2 = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]{20,200000}?)(?:</script>|$)", page)
        raw_json = m2.group(1) if m2 else ""
    if state is None and raw_json:
        # 太长/含函数时，用正则抽字段
        for key, pat in (
            ("author", r'"author"\s*:\s*"([^"]+)"'),
            ("bookName", r'"bookName"\s*:\s*"([^"]+)"'),
            # 连载状态只用 creationStatus/creation_status，不用页面上架态 "status"
            ("creationStatus", r'"creationStatus"\s*:\s*(\d+)'),
            ("creation_status", r'"creation_status"\s*:\s*(\d+)'),
            ("abstract", r'"abstract"\s*:\s*"([^"]*)"'),
            ("thumb", r'"thumb_url"\s*:\s*"([^"]+)"'),
            ("wordCount", r'"(?:wordNumber|wordCount|word_count)"\s*:\s*(\d+)'),
        ):
            mm = re.search(pat, raw_json)
            if not mm:
                continue
            if key == "author" and not hit.author:
                hit.author = _clean(mm.group(1))
            elif key == "bookName" and not hit.name:
                hit.name = _clean(mm.group(1))
            elif key in ("creationStatus", "creation_status"):
                hit.status = _status_from_code(mm.group(1)) or hit.status
            elif key == "abstract" and not hit.intro:
                hit.intro = _clean(mm.group(1))[:500]
            elif key == "thumb" and not hit.cover_url:
                u = mm.group(1).encode().decode("unicode_escape") if "\\u" in mm.group(1) else mm.group(1)
                hit.cover_url = u
            elif key == "wordCount" and not hit.word_count:
                try:
                    hit.word_count = int(mm.group(1))
                except ValueError:
                    pass
        # categoryV2 字符串兜底
        if not hit.category:
            cm = re.search(r'"categoryV2"\s*:\s*"((?:\\.|[^"\\])*)"', raw_json)
            if cm:
                try:
                    cat_raw = json.loads('"' + cm.group(1) + '"')
                except json.JSONDecodeError:
                    cat_raw = cm.group(1)
                names = _names_from_category_v2(cat_raw)
                hit.category = _category_from_names(names)
                hit.tags = [clean_tag_token(x) for x in names if clean_tag_token(x)][:8]
    if isinstance(state, dict):
        page_st = state.get("page") or {}
        if not isinstance(page_st, dict):
            page_st = {}
        if not hit.author:
            hit.author = _clean(page_st.get("author") or "")
        if not hit.name:
            hit.name = _clean(page_st.get("bookName") or "")
        # 连载状态：creationStatus（camelCase）/ creation_status；忽略上架态 status
        if not hit.status:
            hit.status = _status_from_code(
                page_st.get("creationStatus", page_st.get("creation_status"))
            )
        if not hit.intro:
            hit.intro = _clean(page_st.get("abstract") or "")[:500]
        if not hit.category:
            names = _names_from_category_v2(page_st.get("categoryV2") or page_st.get("category"))
            if names:
                hit.category = _category_from_names(names)
                hit.tags = [clean_tag_token(x) for x in names if clean_tag_token(x)][:8]
        # 字数：优先取 JSON 字段（详情页是 wordNumber）
        if not hit.word_count:
            for k in ("wordNumber", "wordCount", "word_count", "totalWordCount"):
                try:
                    v = int(page_st.get(k) or 0)
                except (TypeError, ValueError):
                    v = 0
                if v > 0:
                    hit.word_count = v
                    break

    # 简介：目录前正文段 / abstract / meta description
    if not hit.intro:
        m = re.search(
            r'class="[^"]*(?:page-abstract|book-abstract|abstract|book-info)[^"]*"[^>]*>([\s\S]{10,800}?)</(?:p|div)>',
            page,
        )
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(
            r'作品简介</(?:span|h3|div|p)>\s*([\s\S]{20,800}?)(?:</p></div><div class="page-directory-header"|<div class="page-directory-header")',
            page,
        )
        if m:
            hit.intro = _clean(m.group(1))[:500]
    if not hit.intro:
        m = re.search(
            r'>([^<]{20,400})</p></div><div class="page-directory-header"', page
        )
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
        # 只认连载字段，避免把页面上架态 "status":1 误成连载
        m = re.search(r'"creationStatus"\s*:\s*(\d+)', page) or re.search(
            r'"creation_status"\s*:\s*(\d+)', page
        )
        if m:
            hit.status = _status_from_code(m.group(1))
    if hit.category:
        hit.category = map_category(hit.category)
    # 字数兜底：详情页可见的「xx.x 万字」/「xxxx 字」
    if not hit.word_count:
        m = re.search(r"(\d+(?:\.\d+)?)\s*万字", page)
        if m:
            hit.word_count = int(float(m.group(1)) * 10000)
        else:
            m = re.search(r"(\d{2,9})\s*字", page)
            if m:
                try:
                    hit.word_count = int(m.group(1))
                except ValueError:
                    pass
    if not hit.tags and hit.category:
        hit.tags = [clean_tag_token(x) for x in re.split(r"[,，]", hit.category) if clean_tag_token(x)]
    # 简介兜底：目录前长段落
    if not hit.intro or hit.intro.strip() in ("作品简介", "简介"):
        m = re.search(r">([^<]{30,600})</p></div><div class=\"page-directory-header\"", page)
        if m:
            hit.intro = _clean(m.group(1))[:500]
    return hit


def download_cover(url: str, dest) -> str:
    if not url:
        raise ScrapeError("没有封面地址")
    if url.startswith("//"):
        url = "https:" + url
    try:
        data, ctype = http_get_bytes(
            url, headers={"Referer": "https://fanqienovel.com/"}, timeout=TIMEOUT
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
