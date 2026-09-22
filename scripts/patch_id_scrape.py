from pathlib import Path

p = Path("app/scrapers/qidian.py")
t = p.read_text(encoding="utf-8")
if "def extract_book_id" not in t:
    needle = 'def book_url_for(book_id: str) -> str:\n    return f"https://www.qidian.com/book/{book_id}/"'
    add = needle + '''

def extract_book_id(text: str) -> str:
    """从 URL 或纯数字提取起点 bookId。"""
    s = (text or "").strip()
    m = re.search(r"qidian\\.com/(?:book|info)/(\\d{5,12})", s)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\\d{5,12})", s)
    return m.group(1) if m else ""
'''
    if needle in t:
        t = t.replace(needle, add, 1)
        p.write_text(t, encoding="utf-8")

p = Path("app/routers/scrape.py")
t = p.read_text(encoding="utf-8")
old = """@router.post(\"/detail\")
def scrape_detail(payload: ApplyIn) -> dict:
    mod = _mod(payload.source)
    try:
        hit = mod.fetch_detail(payload.source_book_id)
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e
    return hit.to_dict()"""
new = """@router.post(\"/detail\")
def scrape_detail(payload: ApplyIn) -> dict:
    mod = _mod(payload.source)
    raw = (payload.source_book_id or \"\").strip()
    extract = getattr(mod, \"extract_book_id\", None)
    bid = (extract(raw) if extract else raw) or raw
    try:
        hit = mod.fetch_detail(bid)
    except ScrapeError as e:
        raise HTTPException(502, str(e)) from e
    return hit.to_dict()"""
if old in t:
    t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")

p = Path("admin.js")
t = p.read_text(encoding="utf-8")
old = """    const keyword = (els.scrapeKeyword.value || els.editTitle.value || \"\").trim();
    if (!keyword) {
      toast(\"请填写搜索关键词\", \"err\");
      return;
    }
    els.scrapeSearchBtn.disabled = true;"""
new = """    const keyword = (els.scrapeKeyword.value || els.editTitle.value || \"\").trim();
    if (!keyword) {
      toast(\"请填写书名或书号/链接\", \"err\");
      return;
    }
    const src0 = (els.scrapeSource && els.scrapeSource.value) || \"qidian\";
    const idLike = /^\\d{5,24}$/.test(keyword) || /qidian\\.com\\/book\\/\\d+|fanqienovel\\.com\\/page\\/\\d+/.test(keyword);
    if (idLike) {
      els.scrapeSearchBtn.disabled = true;
      els.scrapeResults.innerHTML = '<div class=\"muted tiny\">按书号拉取详情…</div>';
      try {
        const res = await api(\"/api/admin/scrape/detail\", {
          method: \"POST\",
          body: { source: src0, source_book_id: keyword },
        });
        const hit = Object.assign({}, res, { source_id: res.source_id || keyword });
        renderScrapeHits([hit], els.editTitle.value);
        askScrapeConfirm(hit);
      } catch (err) {
        els.scrapeResults.innerHTML = '<div class=\"muted tiny\">' + escapeHtml(err.message || \"详情失败\") + \"</div>\";
        toast(err.message || \"详情失败\", \"err\");
      } finally {
        els.scrapeSearchBtn.disabled = false;
      }
      return;
    }
    els.scrapeSearchBtn.disabled = true;"""
if old in t:
    t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")

p = Path("index.html")
t = p.read_text(encoding="utf-8")
t = t.replace('placeholder="搜索关键词（默认当前书名）"', 'placeholder="书名 / 书号 / 详情链接"')
p.write_text(t, encoding="utf-8")
print("id-scrape patched")
