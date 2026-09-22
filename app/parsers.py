"""TXT 章节解析：常见中文章节标题规则 + 文件名元数据。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 常见章节行：第X章/节/回/卷/篇、Chapter N、卷X、序章/楔子/番外 等
CHAPTER_PATTERNS = [
    re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千两〇]+[章回节卷篇集部]\s*[：:.\-—　 ]*\s*(.*)$", re.I),
    re.compile(r"^\s*第\s*[0-9]+\s*[章回节卷篇集部]\b\s*(.*)$", re.I),
    re.compile(r"^\s*(?:Chapter|CHAPTER)\s*[0-9]+\b\s*(.*)$", re.I),
    re.compile(r"^\s*卷\s*[0-9零一二三四五六七八九十百千两〇]+\s*[：:.\-—　 ]*\s*(.*)$", re.I),
    re.compile(r"^\s*(序章|楔子|前言|引子|后记|番外|终章|尾声|完结感言)\s*[：:.\-—　 ]*\s*(.*)$"),
]

FILENAME_PATTERNS = [
    re.compile(r"^(?P<title>.+?)[\s_\-\[\(（]+(?P<author>[^\[\]()（）_\-]{2,20})[\s_\-\]\)）]*$"),
    re.compile(r"^(?P<title>.+?)\((?P<author>[^)]+)\)$"),
    re.compile(r"^(?P<title>.+?)（(?P<author>[^）]+)）$"),
    re.compile(r"^(?P<author>[^\s_\-]+)[\s_\-]+(?P<title>.+)$"),
]


@dataclass
class ParsedChapter:
    title: str
    content: str


@dataclass
class ParsedBook:
    title: str
    author: str
    category: str
    chapters: list[ParsedChapter] = field(default_factory=list)
    word_count: int = 0
    intro: str = ""


_AUTHOR_SUFFIX = re.compile(r"(著|作品|文)$")


def parse_filename_meta(stem: str, category: str) -> tuple[str, str]:
    """从文件名推断书名与作者。支持：书名、书名(作者)、作者-书名 等。"""
    name = stem.strip()
    for pat in FILENAME_PATTERNS:
        m = pat.match(name)
        if not m:
            continue
        gd = m.groupdict()
        title = (gd.get("title") or "").strip()
        author = (gd.get("author") or "").strip()
        if title and author and len(title) >= 1 and title != author:
            author = _AUTHOR_SUFFIX.sub("", author).strip() or author
            return title, author or "佚名"
    return name, "佚名"


def _is_chapter_heading(line: str) -> tuple[bool, str]:
    s = line.strip()
    if not s or len(s) > 80:
        return False, ""
    if s.count("，") >= 2 or s.count("。") >= 1:
        return False, ""
    for pat in CHAPTER_PATTERNS:
        m = pat.match(s)
        if m:
            # 去掉多余空白，保留标题
            title = re.sub(r"\s+", " ", s).strip()
            return True, title
    return False, ""


def parse_txt_text(text: str, default_title: str) -> list[ParsedChapter]:
    """按章节标题切分正文。无法识别时整本作为单章。"""
    # 统一换行，去掉 BOM / 空白行开头
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lines = text.split("\n")

    chapters: list[ParsedChapter] = []
    current_title = default_title
    buf: list[str] = []

    def flush() -> None:
        content = "\n".join(buf).strip()
        # 压缩过多空行
        content = re.sub(r"\n{3,}", "\n\n", content)
        if content or chapters:
            chapters.append(ParsedChapter(title=current_title or default_title, content=content))
        buf.clear()

    for line in lines:
        ok, title = _is_chapter_heading(line)
        if ok:
            # 若缓冲区里已有大量正文，认为是新章；若还在文首，替换默认标题
            body = "".join(buf).strip()
            if body:
                flush()
                current_title = title
            else:
                current_title = title
            continue
        buf.append(line)

    flush()

    # 丢弃开头空章节（无内容且标题非章节名）
    cleaned = [c for c in chapters if c.content.strip()]
    if not cleaned:
        cleaned = [ParsedChapter(title=default_title, content=text.strip())]
    return cleaned


def load_txt_book(path: Path, category: str) -> ParsedBook:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    title, author = parse_filename_meta(path.stem, category)
    chapters = parse_txt_text(text, default_title=title)
    word_count = sum(len(c.content) for c in chapters)

    intro = ""
    if chapters:
        head = chapters[0].content.strip().replace("\n", " ")
        intro = head[:200] + ("…" if len(head) > 200 else "")

    return ParsedBook(
        title=title,
        author=author,
        category=category,
        chapters=chapters,
        word_count=word_count,
        intro=intro,
    )


def load_txt_book_from_text(text: str, stem: str, category: str) -> ParsedBook:
    """从内存文本构建书籍（WebDAV 导入用）。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    title, author = parse_filename_meta(stem, category)
    chapters = parse_txt_text(text, default_title=title)
    word_count = sum(len(c.content) for c in chapters)
    intro = ""
    if chapters:
        head = chapters[0].content.strip().replace("\n", " ")
        intro = head[:200] + ("…" if len(head) > 200 else "")
    return ParsedBook(
        title=title,
        author=author,
        category=category,
        chapters=chapters,
        word_count=word_count,
        intro=intro,
    )
