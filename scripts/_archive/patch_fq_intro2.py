from pathlib import Path

p = Path("app/scrapers/fanqie.py")
t = p.read_text(encoding="utf-8")
if "简介兜底" in t:
    print("already")
else:
    key = "    return hit"
    i = t.rfind(key)
    insert = '''    # 简介兜底：目录前长段落
    if not hit.intro or hit.intro.strip() in ("作品简介", "简介"):
        m = re.search(r">([^<]{30,600})</p></div><div class=\\"page-directory-header\\"", page)
        if m:
            hit.intro = _clean(m.group(1))[:500]
    return hit'''
    if i >= 0:
        t = t[:i] + insert + t[i + len(key):]
        p.write_text(t, encoding="utf-8")
        print("ok")
    else:
        print("no return")
