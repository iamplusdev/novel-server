"""TXT 章节解析：常见中文章节标题规则 + 文件名元数据 + 编码识别（流式）。"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# 中文数字 + 半角/全角阿拉伯数字 + 大写（壹贰…）数字
_NUM = "0-9０-９零〇一二三四五六七八九十百千万亿两廿卅壹贰叁肆伍陆柒捌玖拾佰仟"
_UNIT = "章回节卷篇集部"
# 标题后紧跟这些符号视为“标题/正文分隔符”
_TITLE_SEPS = " \u3000:：、.．。·・-—－_|/\\【】[]（）()"
_SENT_END = "。！？；!?;"

# 常见章节行：第X章/节/回/卷/篇、卷X、Chapter N、序章/楔子/番外 等
CHAPTER_PATTERNS = [
    re.compile(rf"^\s*第\s*[{_NUM}]+\s*[{_UNIT}]\s*(.*)$", re.I),
    re.compile(rf"^\s*卷\s*[{_NUM}]+\s*(.*)$", re.I),
    re.compile(r"^\s*(?:Chapter|CHAPTER)\s*[0-9０-９]+\b\s*(.*)$", re.I),
    re.compile(r"^\s*(序章|序言|楔子|前言|引子|后记|番外|终章|尾声|完结感言|后序|跋)\s*(.*)$"),
]
# “无换行”长文本的虚拟切分：在每个章标记前插入断点
_CHAPTER_MARK_RE = re.compile(rf"(?=第\s*[{_NUM}]+\s*[{_UNIT}])")
_SENT_END_RE = re.compile("[" + re.escape(_SENT_END) + "]")
_LONG_LINE_MIN = 2000  # 超过该长度且含多个章标记的行，按标记切分

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


class ParseCancelled(Exception):
    """导入中途被取消（超大文件解析过程中）。"""


_AUTHOR_SUFFIX = re.compile(r"(著|作品|文)$")

# 编码候选：用采样“择优”而非固定顺序，避免 gb18030 抢先污染 big5 等
_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16", "utf-16-le")
_ENCODING_SAMPLE = 256 * 1024
_REPLACEMENT = "\ufffd"
# 明显“解码错误”的字符：替换符 + 私用区（gb18030 误读 Big5 常落这里）
_BAD_RE = re.compile(r"[\ufffd\ue000-\uf8ff]")
# 采样是 head+mid 拼接，接缝可能截断多字节字符产生 1~2 个替换符，容忍之
_BAD_TOLERATE = 2


def _is_bom(sample: bytes) -> bool:
    return sample.startswith((b"\xff\xfe", b"\xfe\xff"))


def _bad_count(sample: bytes, enc: str) -> int | None:
    """采样按 enc 解码后的“坏字符”数（替换符 + 私用区）；不可用返回 None。

    - utf-16/utf-16-le/be 仅在带 BOM 时才参与：否则一次性 decode 会把单字节文本
      两两配对读成乱码（0 个替换符但全是错字），从而错误胜出。
    - 用 errors="replace" 解码，避免采样接缝截断多字节字符时整档编码被判“不可用”。
    """
    if enc.startswith("utf-16") and not _is_bom(sample):
        return None
    try:
        text = sample.decode(enc, errors="replace")
    except LookupError:
        return None
    return max(0, len(_BAD_RE.findall(text)) - _BAD_TOLERATE)


def detect_encoding(sample: bytes) -> str:
    """采样择优给出最可能的编码：BOM 优先，其次坏字符最少（同分按优先级）。"""
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if _is_bom(sample):
        return "utf-16"
    fallback = None
    for enc in _ENCODINGS:
        n = _bad_count(sample, enc)
        if n == 0:
            return enc
        if n is not None and fallback is None:
            fallback = enc
    return fallback or "utf-8"


def decode_bytes(raw: bytes) -> str:
    """整段解码：先按采样择优，严格失败再以 replace 兜底。"""
    if not raw:
        return ""
    enc = detect_encoding(raw[:_ENCODING_SAMPLE])
    try:
        return raw.decode(enc)
    except (UnicodeError, LookupError):
        return raw.decode(enc, errors="replace")


def _sample_file(path: Path) -> bytes:
    """取文件头 + 中段样本用于编码识别（避免纯 ASCII 头部导致误判）。"""
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(_ENCODING_SAMPLE)
        mid = b""
        if size > 2 * _ENCODING_SAMPLE:
            f.seek(size // 2)
            mid = f.read(_ENCODING_SAMPLE)
    return head + mid


class _HashingRaw(io.RawIOBase):
    """只读包装：边读边累计 SHA-256，实现“解析即哈希”的单次读盘。"""

    def __init__(self, fh) -> None:
        self._fh = fh
        self.hash = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        n = self._fh.readinto(b)
        if n:
            self.hash.update(memoryview(b)[:n])
        return n or 0


def parse_filename_meta(stem: str, category: str) -> tuple[str, str]:
    """从文件名推断书名与作者。支持《书名》（校对版全本）作者：某某 等。"""
    name = stem.strip()
    name = re.sub(r"\.txt$", "", name, flags=re.I).strip()

    m = re.search(r"作者\s*[：:]\s*(.+)$", name)
    author_inline = ""
    if m:
        author_inline = m.group(1).strip()
        name = name[: m.start()].strip()

    def clean_title(t: str) -> str:
        t = (t or "").strip().strip("《》")
        t = re.sub(r"[（(][^）)]*?(?:校对|精校|全本|修订|完本)[^）)]*[）)]", "", t)
        return re.sub(r"\s+", " ", t).strip()

    def clean_author(a: str) -> str:
        a = (a or "").strip()
        if re.search(r"(校对|精校|全本|修订|完本)", a):
            return ""
        a = re.sub(r"(著|作品|文)$", "", a).strip()
        return a

    for pat in FILENAME_PATTERNS:
        m = pat.match(name)
        if not m:
            continue
        gd = m.groupdict()
        title = clean_title(gd.get("title") or "")
        author = clean_author(gd.get("author") or "")
        if title and (author or author_inline):
            return title, (author_inline or author or "佚名").strip() or "佚名"
        if title and author_inline:
            return title, clean_author(author_inline) or "佚名"

    if author_inline:
        return clean_title(name) or stem, clean_author(author_inline) or "佚名"
    return clean_title(name) or stem, "佚名"


def _split_line_by_markers(line: str) -> list[str]:
    """把含多个章标记的行按标记切开（应对“多章标题排在同一行 / 整本不换行”）。"""
    if len(_CHAPTER_MARK_RE.findall(line)) < 2:
        return [line]
    parts = [p for p in _CHAPTER_MARK_RE.split(line) if p and p.strip()]
    return parts if len(parts) >= 2 else [line]


def _match_heading(line: str) -> tuple[bool, str, str]:
    """判断一行是否为章节标题，返回 (是否标题, 标题, 同行正文)。

    标题与正文排在同一行时（如「第一章 重生。夜色沉沉…」），标题取到首个句末标点前，
    其余作为“同行正文”并入该章内容，避免正文被丢弃。
    """
    s = line.strip()
    if not s:
        return False, "", ""
    for pat in CHAPTER_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        title_raw = m.group(1) or ""
        # 数字/单位后是否带分隔符（空格/标点）：注意正则已吞掉空白，需看 group1 前一字符
        before = s[m.start(1) - 1] if m.start(1) > 0 else ""
        has_sep = before.isspace() or (bool(title_raw) and title_raw[0] in _TITLE_SEPS)
        # 无分隔符且“标题”很长 → 判为正文（如「第一章的内容他早忘了」）
        if title_raw and not has_sep and len(title_raw) > 6:
            return False, "", ""
        mm = _SENT_END_RE.search(title_raw)
        cut = m.start(1) + (mm.start() if mm else len(title_raw))
        title = s[:cut].strip().rstrip("，,、;；:：")
        if not title or len(title) > 40:
            return False, "", ""
        body = s[cut:].strip()
        return True, title, body
    return False, "", ""


def _is_chapter_heading(line: str) -> tuple[bool, str]:
    """兼容旧签名：仅返回 (是否标题, 标题)。"""
    ok, title, _body = _match_heading(line)
    return ok, title


def iter_chapters(lines: Iterable[str], cancel=None) -> Iterator[ParsedChapter]:
    """逐行流式切章：迭代文本行（可含换行），边读边产出章节，避免整本驻留内存。

    无法识别章节标题时，整本作为单章（标题留空）产出。
    cancel（threading.Event）置位时抛 ParseCancelled，供导入中途中断。
    """
    current_title = ""
    buf: list[str] = []
    emitted = 0
    first = True
    checked = 0

    def finish() -> str:
        content = "\n".join(buf).strip()
        # 压缩过多空行
        return re.sub(r"\n{3,}", "\n\n", content)

    for raw in lines:
        # 每若干行检查一次取消，避免超大文件一直跑
        checked += 1
        if cancel is not None and (checked & 1023) == 0 and cancel.is_set():
            raise ParseCancelled()
        raw = raw.rstrip("\r\n")
        if first:
            first = False
            raw = raw.lstrip("\ufeff")
        # 无换行/多章标题串排：先按章标记切分成多段再逐段判定
        for line in _split_line_by_markers(raw):
            ok, title, inline = _match_heading(line)
            if ok:
                # 缓冲区已有正文则先落盘，否则直接采用该章标题
                body = "".join(buf).strip()
                if body:
                    content = finish()
                    buf.clear()
                    if content or emitted:
                        emitted += 1
                        yield ParsedChapter(title=current_title, content=content)
                    current_title = title
                else:
                    buf.clear()
                    current_title = title
                # 标题与正文同行时，标题后的正文并入本章
                if inline:
                    buf.append(inline)
                continue
            buf.append(line)

    content = finish()
    buf.clear()
    if content or emitted:
        yield ParsedChapter(title=current_title, content=content)


def parse_txt_text(text: str) -> list[ParsedChapter]:
    """按章节标题切分正文（内存版）。无法识别时整本作为单章。"""
    # 统一换行，去掉 BOM / 空白行开头
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cleaned = [c for c in iter_chapters(io.StringIO(text)) if c.content.strip()]
    if not cleaned:
        # 整本无法识别章节时：单章标题留空，前端回退「第 1 章」
        cleaned = [ParsedChapter(title="", content=text.strip())]
    return cleaned


def _build_parsed(stem: str, category: str, chapters: list[ParsedChapter]) -> ParsedBook:
    title, author = parse_filename_meta(stem, category)
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


def _resolve_stream_encoding(sample: bytes) -> str:
    """流式读取用的编码：utf-16 按 BOM 落成具体端序。

    直接用 "utf-16" 编解码器要求首块必须是 BOM，否则抛 UnicodeError（errors=replace 也压不住），
    故这里按 BOM 明确端序（utf-16-le/be），由 iter_chapters 去掉开头的 \\ufeff。
    """
    if sample.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if sample.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return detect_encoding(sample)


def load_txt_book_with_hash(path: Path, category: str, cancel=None) -> tuple[ParsedBook, str]:
    """流式解析文件并返回 (ParsedBook, sha256)。单次读盘：边读边算哈希与切章。

    cancel 置位时抛 ParseCancelled（超大文件解析中途可中断）。
    任何编码异常都会退化为整段兜底解码，保证导入不因编码失败。
    """
    enc = _resolve_stream_encoding(_sample_file(path))
    try:
        with path.open("rb") as fh:
            raw = _HashingRaw(fh)
            text = io.TextIOWrapper(
                io.BufferedReader(raw), encoding=enc, errors="replace", newline=None
            )
            chapters = [c for c in iter_chapters(text, cancel=cancel) if c.content.strip()]
            text.detach()  # 不关闭底层文件，交由 with 收尾
        digest = raw.hash.hexdigest()
    except (UnicodeError, LookupError):
        # 非规范/损坏编码：整段兜底解码（decode_bytes 已按择优选择），保证可导入
        data = path.read_bytes()
        chapters = [
            c for c in iter_chapters(io.StringIO(decode_bytes(data)), cancel=cancel) if c.content.strip()
        ]
        digest = hashlib.sha256(data).hexdigest()
    if not chapters:
        chapters = [ParsedChapter(title="", content="")]
    return _build_parsed(path.stem, category, chapters), digest


def load_txt_book(path: Path, category: str) -> ParsedBook:
    parsed, _digest = load_txt_book_with_hash(path, category)
    return parsed


def load_txt_book_from_text(text: str, stem: str, category: str) -> ParsedBook:
    """从内存文本构建书籍（重解析 / WebDAV 导入用）。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return _build_parsed(stem, category, parse_txt_text(text))
