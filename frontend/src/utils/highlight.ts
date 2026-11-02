export interface HighlightPart {
  text: string;
  hit: boolean;
}

/** 按关键词切分文本用于高亮（大小写不敏感，纯文本匹配） */
export function highlightParts(text: string, keyword: string): HighlightPart[] {
  const needle = (keyword || "").trim();
  if (!needle) return [{ text, hit: false }];
  const low = text.toLowerCase();
  const n = needle.toLowerCase();
  const parts: HighlightPart[] = [];
  let from = 0;
  while (from < text.length) {
    const at = low.indexOf(n, from);
    if (at < 0) break;
    if (at > from) parts.push({ text: text.slice(from, at), hit: false });
    parts.push({ text: text.slice(at, at + n.length), hit: true });
    from = at + n.length;
  }
  if (from < text.length) parts.push({ text: text.slice(from), hit: false });
  return parts.length ? parts : [{ text, hit: false }];
}
