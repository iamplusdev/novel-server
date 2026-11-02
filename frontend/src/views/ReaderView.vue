<script setup lang="ts">
/**
 * 独立全屏阅读页（不嵌管理后台）：目录可收缩 / 正文 / 排版 / 进度。
 * 正文与完整目录走公开 API；进度写回管理端。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  chapterHeading,
  fetchAllBookChapters,
  fetchBook,
  fetchChapterContent,
  isTocPlaceholder,
  pullBookProgress,
  searchBookContent,
  updateReadProgress,
} from "@/api/admin";
import AppIcon from "@/components/AppIcon.vue";
import type { BookSearchHit } from "@/api/admin";
import type { BookDetail } from "@/api/types";

interface TocItem {
  id: number;
  index: number;
  title: string;
}

type ReaderTheme = "paper" | "warm" | "night";
type ReaderFont = "serif" | "sans" | "system";

const FONT_STACKS: Record<ReaderFont, string> = {
  serif: '"Songti SC", SimSun, "Noto Serif CJK SC", serif',
  sans: '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif',
  system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
};

const fontOptions: { value: ReaderFont; label: string; stack: string }[] = [
  { value: "serif", label: "宋体", stack: FONT_STACKS.serif },
  { value: "sans", label: "黑体", stack: FONT_STACKS.sans },
  { value: "system", label: "系统", stack: FONT_STACKS.system },
];

const route = useRoute();
const router = useRouter();

const book = ref<BookDetail | null>(null);
const loading = ref(false);
const contentLoading = ref(false);
const chapterText = ref("");
const chapterError = ref("");
const tocItems = ref<TocItem[]>([]);
const tocTotal = ref(0);
/** 目录侧栏开合（记忆到 localStorage） */
const tocOpen = ref(localStorage.getItem("novel_read_toc") !== "0");
const settingsOpen = ref(false);

/** 书内搜索面板 */
const searchOpen = ref(false);
const searchQuery = ref("");
const searchLoading = ref(false);
const searchError = ref("");
const searchHits = ref<BookSearchHit[]>([]);
const searchTotal = ref(0);
const searchInputEl = ref<HTMLInputElement | null>(null);
/** 搜索请求序号：快速连续搜索时丢弃过期响应 */
let searchSeq = 0;

/** 沉浸模式：阅读时自动收起顶栏 */
const autoHideTopbar = ref(localStorage.getItem("novel_read_autohide") !== "0");
const topbarHidden = ref(false);
let topbarTimer: ReturnType<typeof setTimeout> | undefined;
/** 程序化滚动（切章恢复位置）不参与显示/隐藏判断 */
let scrollSuppressed = false;
let lastScrollTop = 0;
/** 窄屏：目录以覆盖抽屉展示 */
const isNarrow = ref(window.innerWidth < 900);
const isFullscreen = ref(false);
const activeChapterId = ref<number | null>(null);

const fontSize = ref(Number(localStorage.getItem("novel_read_font") || 18));
const lineHeight = ref(Number(localStorage.getItem("novel_read_leading") || 1.8));
const readerTheme = ref<ReaderTheme>(
  (localStorage.getItem("novel_read_theme") as ReaderTheme) || "paper",
);
/** 正文字体：宋体 / 黑体 / 系统 */
const readerFont = ref<ReaderFont>((() => {
  const saved = localStorage.getItem("novel_read_font_family") as ReaderFont | null;
  return saved && saved in FONT_STACKS ? saved : "serif";
})());
/** 正文最大宽度（px），窄屏由容器自动收缩 */
const contentWidth = ref((() => {
  const n = Number(localStorage.getItem("novel_read_width") || 720);
  return Number.isFinite(n) ? Math.min(1000, Math.max(560, n)) : 720;
})());

/** 阅读模式：上下滚动（默认）/ 左右翻页 */
const pagedMode = ref(localStorage.getItem("novel_read_mode") === "paged");
/** 翻页：栏间距、当前页宽、总页数、当前页序号 */
const PAGE_GAP = 48;
const pageWidth = ref(720);
const pageCount = ref(1);
const pageIndex = ref(0);
/** 向上跨章时指定要落到最后一页的章节 id（避免标记串到其它章节） */
let pendingLastPageFor: number | null = null;
const trackEl = ref<HTMLElement | null>(null);
const articleEl = ref<HTMLElement | null>(null);

/** 远端进度带来的章内字符位置（绑定目标章节，只消费一次） */
const pendingRemotePos = ref<{ chapterId: number; pos: number } | null>(null);
/** Beacon 推送节流：pagehide 与 visibilitychange 可能连续触发 */
let lastBeaconAt = 0;

const bookId = computed(() => {
  const raw = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id;
  const n = Number.parseInt(String(raw ?? ""), 10);
  return Number.isInteger(n) && n > 0 ? n : 0;
});

const chapters = computed(() => tocItems.value);
/** 目录展示项：过滤伪占位行（空标题/书名重复）后附带 1 基顺序序号 */
const displayChapters = computed(() => {
  const bookName = book.value?.name;
  const named = tocItems.value.filter((c) => !isTocPlaceholder(c.title, bookName));
  return named.map((c, i) => ({ ...c, no: i + 1 }));
});
/** 目录筛选关键词（标题或章节号） */
const tocFilter = ref("");
const filteredChapters = computed(() => {
  const kw = tocFilter.value.trim().toLowerCase();
  if (!kw) return displayChapters.value;
  return displayChapters.value.filter(
    (c) => c.title.toLowerCase().includes(kw) || String(c.no) === kw,
  );
});
const tocListEl = ref<HTMLElement | null>(null);
const activeChapter = computed(
  () => chapters.value.find((c) => c.id === activeChapterId.value) || chapters.value[0] || null,
);

/** 当前章序号（1 基）与总章数：总章数优先 book.chapter_count / toc.total */
const chapterNo = computed(() => {
  const list = chapters.value;
  const ch = activeChapter.value;
  if (!list.length || !ch) return 0;
  const idx = list.findIndex((c) => c.id === ch.id);
  return idx >= 0 ? idx + 1 : 0;
});
const chapterTotal = computed(() => {
  const fromBook = Number(book.value?.chapter_count) || 0;
  const fromToc = Number(tocTotal.value) || 0;
  return Math.max(fromBook, fromToc, chapters.value.length, 0);
});

/** 顶栏进度文案：第 n / 总 · x%（翻页模式附带页码） */
const progressText = computed(() => {
  const total = chapterTotal.value;
  const n = chapterNo.value;
  if (!total || !n) return "";
  const pageInfo =
    pagedMode.value && pageCount.value > 1 ? ` · ${pageIndex.value + 1}/${pageCount.value} 页` : "";
  return `第 ${n} / ${total} 章 · ${readPercent.value}%${pageInfo}`;
});

const hasPrev = computed(() => chapterNo.value > 1);
const hasNext = computed(() => chapterNo.value > 0 && chapterNo.value < chapterTotal.value);

/** 正文请求序号：快速切章时丢弃过期响应，避免旧章节覆盖新章节 */
let contentSeq = 0;

/** 章内阅读位置：每本书独立存储，仅保留最近 100 章，避免 localStorage 无限增长 */
interface SavedPos {
  id: number;
  top: number;
  t: number;
}
const MAX_SAVED_POS = 100;

function posKey(bid: number): string {
  return `novel_read_pos_${bid}`;
}

function readSavedPositions(bid: number): SavedPos[] {
  try {
    const raw = JSON.parse(localStorage.getItem(posKey(bid)) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

/** 某章上次的滚动位置；无记录返回 0（从章首开始） */
function savedTopFor(chapterId: number): number {
  if (!bookId.value) return 0;
  const item = readSavedPositions(bookId.value).find((p) => p.id === chapterId);
  const top = Number(item?.top);
  return Number.isFinite(top) && top > 0 ? top : 0;
}

/** 记住某本书某章的滚动位置（最近使用的排在前面） */
function rememberPositionFor(bid: number, chapterId: number, top: number) {
  if (!bid || !chapterId) return;
  const list = readSavedPositions(bid).filter((p) => p.id !== chapterId);
  list.unshift({ id: chapterId, top: Math.max(0, Math.round(top)), t: Date.now() });
  try {
    localStorage.setItem(posKey(bid), JSON.stringify(list.slice(0, MAX_SAVED_POS)));
  } catch {
    /* 隐私模式/配额满时忽略，不影响阅读 */
  }
}

function rememberPosition(chapterId: number, top: number) {
  rememberPositionFor(bookId.value, chapterId, top);
}

/** 翻页位置：每本书每章记录页码，保留最近 100 章 */
interface SavedPage {
  id: number;
  page: number;
  t: number;
}
const MAX_SAVED_PAGE = 100;

function pageKey(bid: number): string {
  return `novel_read_page_${bid}`;
}

function readSavedPages(bid: number): SavedPage[] {
  try {
    const raw = JSON.parse(localStorage.getItem(pageKey(bid)) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

function savedPageFor(chapterId: number): number {
  if (!bookId.value) return 0;
  const item = readSavedPages(bookId.value).find((p) => p.id === chapterId);
  const page = Number(item?.page);
  return Number.isFinite(page) && page > 0 ? page : 0;
}

function rememberPageFor(bid: number, chapterId: number, page: number) {
  if (!bid || !chapterId) return;
  const list = readSavedPages(bid).filter((p) => p.id !== chapterId);
  list.unshift({ id: chapterId, page: Math.max(0, Math.round(page)), t: Date.now() });
  try {
    localStorage.setItem(pageKey(bid), JSON.stringify(list.slice(0, MAX_SAVED_PAGE)));
  } catch {
    /* 隐私模式/配额满时忽略 */
  }
}

function rememberPage(chapterId: number, page: number) {
  rememberPageFor(bookId.value, chapterId, page);
}

/** 滚动写入节流（250ms），避免高频读写 localStorage */
let scrollTimer: ReturnType<typeof setTimeout> | undefined;
function onContentScroll() {
  const top = contentEl.value?.scrollTop || 0;
  const delta = top - lastScrollTop;
  lastScrollTop = top;

  // 沉浸阅读：向下读收起顶栏，向上翻立即显示（翻页模式不靠滚动判断）
  if (!scrollSuppressed && !pagedMode.value) {
    if (delta < -8) {
      revealTopbar();
    } else if (delta > 24 && top > 80) {
      clearTopbarTimer();
      if (autoHideTopbar.value && !searchOpen.value && !settingsOpen.value && !tocOpen.value) {
        topbarHidden.value = true;
      }
    }
  }

  const id = activeChapterId.value;
  if (!id) return;
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => {
    // 切章后旧定时器可能才触发，只写回仍处于当前章的位置
    if (activeChapterId.value === id) {
      rememberPosition(id, contentEl.value?.scrollTop || 0);
    }
  }, 250);
}

/** 章节正文内存缓存：预取与回看直接命中，仅保留最近 24 章 */
const CHAPTER_CACHE_MAX = 24;
const chapterCache = new Map<number, string>();
const prefetching = new Set<number>();

function cacheChapter(id: number, text: string) {
  chapterCache.delete(id);
  chapterCache.set(id, text);
  while (chapterCache.size > CHAPTER_CACHE_MAX) {
    const oldest = chapterCache.keys().next().value;
    if (oldest === undefined) break;
    chapterCache.delete(oldest);
  }
}

/** 读取缓存并刷新 LRU 顺序；空正文也是有效缓存 */
function cachedChapter(id: number): string | undefined {
  if (!chapterCache.has(id)) return undefined;
  const text = chapterCache.get(id) as string;
  chapterCache.delete(id);
  chapterCache.set(id, text);
  return text;
}

/** 预取下一章正文，切章时几乎无需等待 */
async function prefetchNextChapter() {
  const list = chapters.value;
  const idx = list.findIndex((c) => c.id === activeChapterId.value);
  const next = idx >= 0 ? list[idx + 1] : undefined;
  if (!next || chapterCache.has(next.id) || prefetching.has(next.id)) return;
  prefetching.add(next.id);
  try {
    const data = await fetchChapterContent(bookId.value, next.id);
    cacheChapter(next.id, data.content || "");
  } catch {
    /* 预取失败不影响当前阅读 */
  } finally {
    prefetching.delete(next.id);
  }
}

/** 测量翻页模式的总页数（横向多栏宽度） */
function measurePaged() {
  const art = articleEl.value;
  if (!pagedMode.value || !art) return;
  const width = pageWidth.value;
  if (width <= 0) return;
  const total = Math.max(1, Math.ceil((art.scrollWidth + PAGE_GAP) / (width + PAGE_GAP)));
  pageCount.value = total;
  if (pageIndex.value > total - 1) pageIndex.value = Math.max(0, total - 1);
}

/** 重新计算页宽与页数（切模式/改字号/改宽度/窗口变化时调用） */
async function relayoutPaged() {
  if (!pagedMode.value || !chapterText.value) return;
  await nextTick();
  const w = trackEl.value?.clientWidth || 0;
  if (w > 0 && w !== pageWidth.value) pageWidth.value = w;
  await nextTick();
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve());
  });
  measurePaged();
}

/** 正文渲染后恢复阅读位置：翻页模式按页码，滚动模式按滚动量 */
async function restoreReadingPosition(chapterId: number, seq: number) {
  if (seq !== contentSeq || !chapterText.value) return;

  // 远端进度位置只对目标章节生效一次
  let remotePos: number | null = null;
  if (pendingRemotePos.value?.chapterId === chapterId) {
    remotePos = pendingRemotePos.value.pos;
    pendingRemotePos.value = null;
  }

  if (pagedMode.value) {
    await relayoutPaged();
    if (seq !== contentSeq) return;
    const wantLast = pendingLastPageFor === chapterId;
    if (wantLast) pendingLastPageFor = null;
    const desired = wantLast
      ? pageCount.value - 1
      : remotePos != null && chapterText.value.length > 0
        ? Math.round((remotePos / chapterText.value.length) * Math.max(0, pageCount.value - 1))
        : savedPageFor(chapterId);
    pageIndex.value = Math.max(0, Math.min(desired, pageCount.value - 1));
    return;
  }

  if (!contentEl.value) return;
  await nextTick();
  if (seq !== contentSeq) return;
  const top = remotePos != null ? scrollTopForChar(remotePos) : savedTopFor(chapterId);
  // 程序化滚动不触发顶栏显示/隐藏
  scrollSuppressed = true;
  contentEl.value.scrollTo({ top, behavior: "auto" });
  lastScrollTop = top;
  requestAnimationFrame(() => {
    scrollSuppressed = false;
  });
}

/** 把章内字符位置近似映射为滚动位置（按段落累计字数） */
function scrollTopForChar(charPos: number): number {
  const el = contentEl.value;
  if (!el || charPos <= 0) return 0;
  const paras = el.querySelectorAll<HTMLElement>(".chapter-body .para");
  let acc = 0;
  for (const p of paras) {
    const len = (p.textContent || "").length;
    if (acc + len >= charPos) {
      const rect = p.getBoundingClientRect();
      const cRect = el.getBoundingClientRect();
      return Math.max(0, el.scrollTop + rect.top - cRect.top - 8);
    }
    acc += len;
  }
  return 0;
}

/** 拉取当前章节正文（优先内存缓存） */
async function loadChapterContent(chapterId: number) {
  if (!bookId.value || !chapterId) return;
  const seq = ++contentSeq;
  chapterError.value = "";

  const cached = cachedChapter(chapterId);
  if (cached !== undefined) {
    contentLoading.value = false;
    chapterText.value = cached;
    await restoreReadingPosition(chapterId, seq);
    void prefetchNextChapter();
    return;
  }

  contentLoading.value = true;
  let ok = false;
  try {
    const data = await fetchChapterContent(bookId.value, chapterId);
    if (seq !== contentSeq) return;
    chapterText.value = data.content || "";
    ok = true;
    cacheChapter(chapterId, chapterText.value);
    if (!chapterText.value) {
      chapterError.value = "本章正文为空";
    }
  } catch (e) {
    if (seq !== contentSeq) return;
    chapterText.value = "";
    chapterError.value = e instanceof Error ? e.message : "正文加载失败";
  } finally {
    if (seq === contentSeq) contentLoading.value = false;
  }
  await restoreReadingPosition(chapterId, seq);
  if (ok) void prefetchNextChapter();
}

/** 按真实总章数换算阅读进度 0–100 */
const readPercent = computed(() => {
  const total = chapterTotal.value;
  const n = chapterNo.value;
  if (!total || !n) return Number(book.value?.read_percent ?? 0) || 0;
  return Math.min(100, Math.round((n / total) * 100));
});

const readerStyle = computed(() => ({
  fontSize: `${fontSize.value}px`,
  lineHeight: String(lineHeight.value),
}));

/** 正文排版：字体族与内容宽度 */
const articleStyle = computed(() => ({
  fontFamily: FONT_STACKS[readerFont.value] || FONT_STACKS.serif,
  maxWidth: `${contentWidth.value}px`,
}));

/** 翻页模式：正文按栏排布，整体横向平移展示当前页 */
const pagedArticleStyle = computed<Record<string, string>>(() => ({
  fontFamily: FONT_STACKS[readerFont.value] || FONT_STACKS.serif,
  columnWidth: `${pageWidth.value}px`,
  columnGap: `${PAGE_GAP}px`,
  columnFill: "auto",
  transform: `translateX(-${pageIndex.value * (pageWidth.value + PAGE_GAP)}px)`,
}));
/** 翻页模式下的内容宽度变量（供 track 的 max-width 使用） */
const pagedVars = computed<Record<string, string>>(() => {
  const vars: Record<string, string> = {};
  if (pagedMode.value) vars["--paged-width"] = `${contentWidth.value}px`;
  return vars;
});

const themeClass = computed(() => `theme-${readerTheme.value}`);

/** 写回阅读进度（百分比 + 章节序号），失败静默不打断阅读 */
async function persistProgress() {
  if (!bookId.value) return;
  try {
    await updateReadProgress(bookId.value, {
      percent: readPercent.value,
      chapter_index: activeChapter.value?.index ?? -1,
    });
    if (book.value) book.value.read_percent = readPercent.value;
  } catch {
    /* 阅读器不阻断 */
  }
}

async function load() {
  if (!bookId.value) return;
  loading.value = true;
  pendingRemotePos.value = null;
  // 与书籍/目录并行拉取远端进度；最多等 2.5 秒，失败不阻塞本地阅读
  const pulledPromise = Promise.race([
    pullBookProgress(bookId.value).catch(() => null),
    new Promise<null>((resolve) => setTimeout(() => resolve(null), 2500)),
  ]);
  try {
    book.value = await fetchBook(bookId.value);
    // 完整目录（按 total 翻页拉全，保证章数/进度正确）
    try {
      const toc = await fetchAllBookChapters(bookId.value);
      tocItems.value = toc.items;
      tocTotal.value = toc.total || toc.items.length;
    } catch {
      tocItems.value = [];
      tocTotal.value = Number(book.value?.chapter_count) || 0;
    }
    const list = chapters.value;
    if (!list.length) return;

    const pulled = await pulledPromise;
    const remoteTarget =
      pulled?.updated && pulled.chapter_id
        ? list.find((c) => c.id === pulled.chapter_id) || null
        : null;

    // 优先级：URL ?chapter= > 远端最新进度 > 本地续读 > 第一章
    const qChapter = Number.parseInt(String(route.query.chapter ?? ""), 10);
    let target = Number.isInteger(qChapter) && qChapter > 0
      ? list.find((c) => c.id === qChapter)
      : null;
    if (!target && remoteTarget) {
      target = remoteTarget;
      if (typeof pulled?.chapter_pos === "number" && pulled.chapter_pos > 0) {
        pendingRemotePos.value = { chapterId: remoteTarget.id, pos: pulled.chapter_pos };
      }
    }
    if (!target) {
      const savedIdx = book.value?.read_chapter_index ?? -1;
      target = savedIdx >= 0 ? list.find((c) => c.index === savedIdx) : null;
    }
    activeChapterId.value = (target || list[0]!).id;
    // 正文由 watch(activeChapterId) 统一加载（含进度写回）
  } catch {
    /* 加载失败不阻断界面 */
  } finally {
    loading.value = false;
  }
}

function persistPrefs() {
  localStorage.setItem("novel_read_font", String(fontSize.value));
  localStorage.setItem("novel_read_leading", String(lineHeight.value));
  localStorage.setItem("novel_read_theme", readerTheme.value);
  localStorage.setItem("novel_read_font_family", readerFont.value);
  localStorage.setItem("novel_read_width", String(contentWidth.value));
  localStorage.setItem("novel_read_autohide", autoHideTopbar.value ? "1" : "0");
  localStorage.setItem("novel_read_mode", pagedMode.value ? "paged" : "scroll");
  localStorage.setItem("novel_read_toc", tocOpen.value ? "1" : "0");
}

function clearTopbarTimer() {
  clearTimeout(topbarTimer);
}

/** 显示顶栏并安排下一次自动收起 */
function revealTopbar() {
  clearTopbarTimer();
  topbarHidden.value = false;
  scheduleTopbarHide();
}

function scheduleTopbarHide() {
  clearTopbarTimer();
  if (!autoHideTopbar.value || searchOpen.value || settingsOpen.value || tocOpen.value) return;
  topbarTimer = setTimeout(() => {
    if (!autoHideTopbar.value || searchOpen.value || settingsOpen.value || tocOpen.value) return;
    // 刚进入/还没开始读时不隐藏；翻页模式看页码/章节进度
    const progressed = pagedMode.value
      ? pageIndex.value > 0 || chapterNo.value > 1
      : (contentEl.value?.scrollTop || 0) >= 120;
    if (!progressed) return;
    topbarHidden.value = true;
  }, 2600);
}

function toggleTopbar() {
  if (topbarHidden.value) {
    revealTopbar();
  } else {
    clearTopbarTimer();
    topbarHidden.value = true;
  }
}

function toggleToc() {
  tocOpen.value = !tocOpen.value;
  localStorage.setItem("novel_read_toc", tocOpen.value ? "1" : "0");
  if (tocOpen.value) revealTopbar();
  else scheduleTopbarHide();
}

function toggleSettings() {
  settingsOpen.value = !settingsOpen.value;
  if (settingsOpen.value) revealTopbar();
  else scheduleTopbarHide();
}

function openSearch() {
  searchOpen.value = true;
  settingsOpen.value = false;
  revealTopbar();
  void nextTick(() => searchInputEl.value?.focus());
}

function toggleSearch() {
  if (searchOpen.value) searchOpen.value = false;
  else openSearch();
}

async function runSearch() {
  const q = searchQuery.value.trim();
  if (!q || !bookId.value) return;
  const seq = ++searchSeq;
  searchLoading.value = true;
  searchError.value = "";
  try {
    const data = await searchBookContent(bookId.value, q);
    if (seq !== searchSeq) return;
    searchHits.value = data.items || [];
    searchTotal.value = Number(data.total) || 0;
    if (!searchHits.value.length) searchError.value = "没有找到相关内容";
  } catch (e) {
    if (seq !== searchSeq) return;
    searchHits.value = [];
    searchTotal.value = 0;
    searchError.value = e instanceof Error ? e.message : "搜索失败";
  } finally {
    if (seq === searchSeq) searchLoading.value = false;
  }
}

function openSearchResult(hit: BookSearchHit) {
  goChapter(hit.chapter_id);
  searchOpen.value = false;
}

interface HighlightPart {
  text: string;
  hit: boolean;
}

/** 片段内高亮关键词（大小写不敏感） */
function highlightParts(text: string, keyword: string): HighlightPart[] {
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

function goBack() {
  // 优先回详情；无历史则回书库
  if (window.history.length > 1) router.back();
  else void router.push({ name: "library" });
}

watch(
  [
    fontSize,
    lineHeight,
    readerTheme,
    tocOpen,
    readerFont,
    contentWidth,
    autoHideTopbar,
    pagedMode,
  ],
  persistPrefs,
);
// 关闭自动隐藏时立即恢复顶栏
watch(autoHideTopbar, (on) => {
  if (!on) revealTopbar();
});
// 切换章节：先记住上一章位置，再同步进度并加载正文
// id 为空是切书重置，位置已由下方 bookId 监听按旧书保存，避免写进新书
watch(activeChapterId, (id, oldId) => {
  if (id && oldId) {
    if (pagedMode.value) rememberPage(oldId, pageIndex.value);
    else rememberPosition(oldId, contentEl.value?.scrollTop || 0);
  }
  // 无有效章节（如切书重置）时不写进度，避免把新书进度清成 0
  if (!id) return;
  pageIndex.value = 0;
  pageCount.value = 1;
  void persistProgress();
  void loadChapterContent(id);
});

// 切换阅读模式：翻页模式重新分页；滚动模式恢复该章滚动位置
watch(pagedMode, async (on) => {
  const id = activeChapterId.value;
  pendingLastPageFor = null;
  if (!id) return;
  if (on) {
    await nextTick();
    await relayoutPaged();
    pageIndex.value = Math.max(0, Math.min(savedPageFor(id), pageCount.value - 1));
  } else if (contentEl.value) {
    await nextTick();
    const top = savedTopFor(id);
    scrollSuppressed = true;
    contentEl.value.scrollTo({ top, behavior: "auto" });
    lastScrollTop = top;
    requestAnimationFrame(() => {
      scrollSuppressed = false;
    });
  }
  scheduleTopbarHide();
});

// 字号/行距/宽度/字体变化后重新分页（滑杆拖动时防抖）
let pagedLayoutTimer: ReturnType<typeof setTimeout> | undefined;
watch([fontSize, lineHeight, contentWidth, readerFont], () => {
  if (!pagedMode.value) return;
  clearTimeout(pagedLayoutTimer);
  pagedLayoutTimer = setTimeout(() => void relayoutPaged(), 120);
});

// 目录/排版面板开合会改变桌面端正文宽度，需要重新分页
watch([tocOpen, settingsOpen], async () => {
  if (!pagedMode.value) return;
  await nextTick();
  await relayoutPaged();
});
// 路由 :id 变化（组件复用）时重置并重新加载，避免显示上一本
watch(bookId, (_next, prev) => {
  // 切书前把当前章位置写回上一本书（此时 bookId 已是新值，需显式传 prev）
  if (prev && activeChapterId.value) {
    rememberPositionFor(prev, activeChapterId.value, contentEl.value?.scrollTop || 0);
  }
  book.value = null;
  tocItems.value = [];
  tocTotal.value = 0;
  chapterText.value = "";
  chapterError.value = "";
  activeChapterId.value = null;
  // 切书时关闭并清空书内搜索
  searchOpen.value = false;
  searchQuery.value = "";
  searchHits.value = [];
  searchTotal.value = 0;
  searchError.value = "";
  // 换书后重置目录筛选、沉浸状态与正文缓存
  tocFilter.value = "";
  clearTopbarTimer();
  scrollSuppressed = false;
  lastScrollTop = 0;
  topbarHidden.value = false;
  pendingLastPageFor = null;
  pendingRemotePos.value = null;
  pageIndex.value = 0;
  pageCount.value = 1;
  chapterCache.clear();
  prefetching.clear();
  void load();
});

/** 目录打开/切章时，把当前章滚动到列表可视区中间 */
function scrollActiveTocIntoView() {
  const id = activeChapterId.value;
  if (!tocOpen.value || !id) return;
  void nextTick(() => {
    const list = tocListEl.value;
    const el = list?.querySelector<HTMLElement>(`[data-chapter-id="${id}"]`);
    if (!list || !el) return;
    const listRect = list.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const delta = elRect.top - listRect.top - list.clientHeight / 2 + el.clientHeight / 2;
    list.scrollTo({ top: Math.max(0, list.scrollTop + delta), behavior: "auto" });
  });
}

watch([tocOpen, activeChapterId], scrollActiveTocIntoView);

function goChapter(id: number) {
  // 窄屏选完章节后收起目录抽屉
  if (isNarrow.value) {
    tocOpen.value = false;
    localStorage.setItem("novel_read_toc", "0");
  }
  if (id === activeChapterId.value) {
    if (pagedMode.value) {
      // 重复点当前章：回到该章上次页码
      pageIndex.value = Math.max(0, Math.min(savedPageFor(id), pageCount.value - 1));
      scheduleTopbarHide();
      return;
    }
    // 重复点当前章：回到该章上次阅读位置
    const top = savedTopFor(id);
    scrollSuppressed = true;
    contentEl.value?.scrollTo({ top, behavior: "auto" });
    lastScrollTop = top;
    requestAnimationFrame(() => {
      scrollSuppressed = false;
    });
    return;
  }
  activeChapterId.value = id;
}

/** 翻页模式：下一页 / 下一章 */
function nextPage() {
  if (!pagedMode.value) return;
  if (pageIndex.value + 1 < pageCount.value) {
    pageIndex.value += 1;
    const id = activeChapterId.value;
    if (id) rememberPage(id, pageIndex.value);
    scheduleTopbarHide();
    return;
  }
  if (hasNext.value) goNextChapter();
}

/** 翻页模式：上一页 / 上一章（跨章落到上一章最后一页） */
function prevPage() {
  if (!pagedMode.value) return;
  if (pageIndex.value > 0) {
    pageIndex.value -= 1;
    const id = activeChapterId.value;
    if (id) rememberPage(id, pageIndex.value);
    scheduleTopbarHide();
    return;
  }
  const list = chapters.value;
  const n = chapterNo.value;
  const target = n > 1 ? list[n - 2] : undefined;
  if (target) {
    pendingLastPageFor = target.id;
    goChapter(target.id);
  }
}

function goPrevChapter() {
  const list = chapters.value;
  const n = chapterNo.value;
  if (n <= 1 || !list.length) return;
  const target = list[n - 2];
  if (target) goChapter(target.id);
}

function goNextChapter() {
  const list = chapters.value;
  const n = chapterNo.value;
  if (!list.length || n < 1 || n >= list.length) return;
  const target = list[n];
  if (target) goChapter(target.id);
}

const contentEl = ref<HTMLElement | null>(null);

async function toggleFullscreen() {
  const el = document.documentElement;
  try {
    if (!document.fullscreenElement) {
      await el.requestFullscreen();
      isFullscreen.value = true;
    } else {
      await document.exitFullscreen();
      isFullscreen.value = false;
    }
  } catch {
    isFullscreen.value = false;
  }
}

function onKeydown(e: KeyboardEvent) {
  // Ctrl/Cmd+F：打开书内搜索并聚焦输入框
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
    e.preventDefault();
    openSearch();
    return;
  }

  if (e.key === "Escape") {
    if (searchOpen.value) {
      searchOpen.value = false;
      searchInputEl.value?.blur();
    }
    settingsOpen.value = false;
    // 窄屏 Esc 关掉目录抽屉
    if (isNarrow.value) tocOpen.value = false;
    return;
  }

  const target = e.target as HTMLElement | null;
  const tag = target?.tagName?.toLowerCase();
  // 输入框/可编辑区域内不接管按键
  if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  if (e.key === "ArrowLeft") {
    e.preventDefault();
    if (pagedMode.value) prevPage();
    else goPrevChapter();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    if (pagedMode.value) nextPage();
    else goNextChapter();
  } else if (e.key === " ") {
    // 空格翻页/下翻一屏，Shift+空格反向
    e.preventDefault();
    if (pagedMode.value) {
      if (e.shiftKey) prevPage();
      else nextPage();
    } else {
      const el = contentEl.value;
      if (el) {
        el.scrollBy({
          top: el.clientHeight * 0.9 * (e.shiftKey ? -1 : 1),
          behavior: "smooth",
        });
      }
    }
  } else if (e.key.toLowerCase() === "t") {
    toggleToc();
  } else if (e.key.toLowerCase() === "h") {
    toggleTopbar();
  }
}

/** 移动端左右滑动切换上下章 */
let touchX = 0;
let touchY = 0;
let touchTracking = false;

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0];
  if (e.touches.length !== 1 || !touch) {
    touchTracking = false;
    return;
  }
  touchTracking = true;
  touchX = touch.clientX;
  touchY = touch.clientY;
}

function onTouchEnd(e: TouchEvent) {
  const touch = e.changedTouches[0];
  if (!touchTracking || e.changedTouches.length !== 1 || !touch) return;
  touchTracking = false;
  const dx = touch.clientX - touchX;
  const dy = touch.clientY - touchY;
  // 轻点正文：唤起顶栏
  if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
    revealTopbar();
    return;
  }
  // 横向位移足够大且明显大于纵向才翻页，避免干扰纵向滚动与文本选择
  if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
  if (pagedMode.value) {
    if (dx < 0) nextPage();
    else prevPage();
  } else if (dx < 0) {
    goNextChapter();
  } else {
    goPrevChapter();
  }
}

/** 翻页模式：点击正文左/右 30% 区域翻页（选中文字或点到按钮时不触发） */
function onContentClick(e: MouseEvent) {
  if (!pagedMode.value) return;
  const target = e.target as HTMLElement | null;
  if (target?.closest("button, a, input, textarea, select")) return;
  if (window.getSelection()?.toString()) return;
  const rect = contentEl.value?.getBoundingClientRect();
  if (!rect) return;
  const x = e.clientX - rect.left;
  if (x < rect.width * 0.3) prevPage();
  else if (x > rect.width * 0.7) nextPage();
}

let pagedResizeTimer: ReturnType<typeof setTimeout> | undefined;

function onResize() {
  isNarrow.value = window.innerWidth < 900;
  if (pagedMode.value) {
    clearTimeout(pagedResizeTimer);
    pagedResizeTimer = setTimeout(() => void relayoutPaged(), 150);
  }
}

/** 桌面端鼠标靠近窗口顶部时唤起顶栏 */
function onMouseMove(e: MouseEvent) {
  if (e.clientY <= 72) revealTopbar();
}

/** 估算章内字符位置（滚动/翻页进度换算，供 Legado 落点参考） */
function estimateChapterPos(): number {
  const text = chapterText.value || "";
  if (!text) return 0;
  if (pagedMode.value && pageCount.value > 1) {
    return Math.round((pageIndex.value / (pageCount.value - 1)) * text.length);
  }
  const el = contentEl.value;
  if (!el) return 0;
  const max = Math.max(1, el.scrollHeight - el.clientHeight);
  return Math.max(0, Math.min(text.length, Math.round((el.scrollTop / max) * text.length)));
}

/** 关闭/隐藏页面时把进度推送到 WebDAV（Beacon 不阻塞页面） */
function pushProgressBeacon() {
  const bid = bookId.value;
  const chid = activeChapterId.value;
  if (!bid || !chid) return;
  const now = Date.now();
  if (now - lastBeaconAt < 4000) return;
  lastBeaconAt = now;
  const body = JSON.stringify({
    chapter_id: chid,
    chapter_pos: estimateChapterPos(),
    client_time: now,
  });
  const url = `/api/admin/books/${bid}/sync/push`;
  // 优先 fetch+keepalive（保留 JSON Content-Type），失败再退回 Beacon
  try {
    void fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      credentials: "include",
      keepalive: true,
    }).catch(() => {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      }
    });
  } catch {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    }
  }
}

function onVisibilityChange() {
  if (document.visibilityState === "hidden") pushProgressBeacon();
}

onMounted(() => {
  void load();
  window.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", onResize);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("pagehide", pushProgressBeacon);
  document.addEventListener("visibilitychange", onVisibilityChange);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", onResize);
  window.removeEventListener("mousemove", onMouseMove);
  window.removeEventListener("pagehide", pushProgressBeacon);
  document.removeEventListener("visibilitychange", onVisibilityChange);
  // 组件内跳转（如返回书库）不会触发 pagehide，这里补一次推送
  pushProgressBeacon();
  clearTimeout(scrollTimer);
  clearTimeout(pagedResizeTimer);
  clearTimeout(pagedLayoutTimer);
  clearTopbarTimer();
  // 离开阅读器时落盘一次章内位置与进度
  if (activeChapterId.value) {
    if (pagedMode.value) rememberPage(activeChapterId.value, pageIndex.value);
    else rememberPosition(activeChapterId.value, contentEl.value?.scrollTop || 0);
  }
  void persistProgress();
});
</script>

<template>
  <div class="reader-root" :class="themeClass">
    <header class="reader-top" :class="{ 'is-hidden': topbarHidden }">
      <!-- 左：返回 + 书名 + 进度 -->
      <div class="top-left">
        <button type="button" class="icon-btn" title="返回" @click="goBack">
          <AppIcon name="back" :size="18" />
        </button>
        <div class="top-title">
          <div class="name-line">
            <span class="name">{{ book?.name || "阅读" }}</span>
            <span v-if="progressText" class="progress-text muted-xs">{{ progressText }}</span>
          </div>
        </div>
      </div>

      <!-- 中：当前章节名（相对视口水平居中） -->
      <div class="top-center">
        <div class="chapter-name">
          {{ activeChapter ? chapterHeading(activeChapter.title, activeChapter.index, book?.name) : "选择章节" }}
        </div>
      </div>

      <!-- 右：操作 -->
      <div class="top-actions">
        <button
          type="button"
          class="icon-btn"
          :class="{ 'is-on': tocOpen }"
          title="目录（T）"
          @click="toggleToc"
        >
          <AppIcon name="list" :size="18" />
        </button>
        <button
          type="button"
          class="icon-btn"
          :class="{ 'is-on': searchOpen }"
          title="书内搜索（Ctrl+F）"
          @click="toggleSearch"
        >
          <AppIcon name="search" :size="18" />
        </button>
        <button
          type="button"
          class="icon-btn"
          :class="{ 'is-on': settingsOpen }"
          title="排版"
          @click="toggleSettings"
        >
          <AppIcon name="type" :size="18" />
        </button>
        <button type="button" class="icon-btn" title="全屏" @click="toggleFullscreen">
          <AppIcon name="full" :size="18" />
        </button>
      </div>
    </header>

    <div
      class="reader-body"
      :class="{
        'toc-collapsed': !tocOpen,
        'set-open': settingsOpen,
        'is-narrow': isNarrow,
      }"
    >
      <!-- 目录：始终占位，收起时 width=0（不 display:none，避免挤掉正文列） -->
      <aside
        class="toc"
        :class="{ 'is-drawer': isNarrow, 'is-closed': !tocOpen }"
      >
        <div class="toc-head">
          <span>目录</span>
          <span v-if="tocFilter" class="toc-count muted-xs">
            {{ filteredChapters.length }}/{{ displayChapters.length }}
          </span>
          <button type="button" class="icon-btn sm" title="收起目录" @click="toggleToc">
            <AppIcon name="back" :size="14" />
          </button>
        </div>
        <div class="toc-search">
          <input
            v-model="tocFilter"
            type="search"
            class="toc-search-input"
            placeholder="筛选章节…"
          />
          <button
            v-if="tocFilter"
            type="button"
            class="toc-clear"
            title="清除筛选"
            @click="tocFilter = ''"
          >
            ×
          </button>
        </div>
        <div ref="tocListEl" class="toc-list">
          <button
            v-for="ch in filteredChapters"
            :key="ch.id"
            type="button"
            class="toc-item"
            :data-chapter-id="ch.id"
            :class="{ 'is-active': ch.id === activeChapter?.id }"
            @click="goChapter(ch.id)"
          >
            <span class="idx">{{ ch.no }}</span>
            <span class="title">{{ ch.title }}</span>
          </button>
          <p v-if="!filteredChapters.length" class="muted toc-empty">
            {{ tocFilter ? "无匹配章节" : "暂无目录" }}
          </p>
        </div>
      </aside>
      <!-- 窄屏点遮罩关目录 -->
      <div
        v-if="isNarrow && tocOpen"
        class="toc-mask"
        @click="toggleToc"
      />

      <!-- 正文区：滚动位置记忆 + 移动端左右滑动翻章 -->
      <main
        ref="contentEl"
        class="content"
        :class="{ 'content-paged': pagedMode }"
        :style="[readerStyle, pagedVars]"
        @scroll.passive="onContentScroll"
        @touchstart.passive="onTouchStart"
        @touchend.passive="onTouchEnd"
        @click="onContentClick"
      >
        <div ref="trackEl" class="paged-track" :class="{ 'is-paged': pagedMode }">
        <article
          ref="articleEl"
          class="article"
          :class="{ 'is-paged': pagedMode }"
          :style="pagedMode ? pagedArticleStyle : articleStyle"
        >
          <h1 class="chapter-title">
            {{ activeChapter ? chapterHeading(activeChapter.title, activeChapter.index, book?.name) : "开始阅读" }}
          </h1>
          <div v-if="contentLoading" class="placeholder-body muted">正文加载中…</div>
          <div v-else-if="chapterError" class="placeholder-body muted">{{ chapterError }}</div>
          <div v-else-if="chapterText" class="chapter-body">
            <p v-for="(para, i) in chapterText.split(/\n+/)" :key="i" class="para">{{ para }}</p>
          </div>
          <div v-else class="placeholder-body muted">
            <p>选择左侧目录开始阅读。</p>
          </div>
          <!-- 章末导航：随正文滚动，不固定视口底部 -->
          <nav class="chapter-nav">
            <button
              type="button"
              class="foot-btn"
              :disabled="!hasPrev"
              @click="goPrevChapter"
            >
              上一章
            </button>
            <button type="button" class="foot-btn" @click="toggleToc">目录</button>
            <button
              type="button"
              class="foot-btn"
              :disabled="!hasNext"
              @click="goNextChapter"
            >
              下一章
            </button>
          </nav>
        </article>
        </div>
      </main>

      <!-- 书内搜索浮层 -->
      <aside v-if="searchOpen" class="search-panel" aria-label="书内搜索">
        <div class="search-head">
          <input
            ref="searchInputEl"
            v-model="searchQuery"
            type="search"
            class="search-input"
            placeholder="在本书中搜索…"
            @keyup.enter="runSearch"
          />
          <button type="button" class="search-btn" :disabled="searchLoading" @click="runSearch">
            {{ searchLoading ? "搜索中" : "搜索" }}
          </button>
          <button type="button" class="icon-btn sm" title="关闭" @click="searchOpen = false">
            ×
          </button>
        </div>
        <div class="search-meta muted-xs">
          <span v-if="searchLoading">正在扫描正文…</span>
          <span v-else-if="searchQuery.trim() && searchHits.length">
            共 {{ searchTotal }} 处匹配
          </span>
          <span v-else-if="searchError">{{ searchError }}</span>
          <span v-else>回车开始搜索</span>
        </div>
        <div class="search-list">
          <button
            v-for="(hit, i) in searchHits"
            :key="`${hit.chapter_id}-${i}`"
            type="button"
            class="search-hit"
            @click="openSearchResult(hit)"
          >
            <span class="hit-title">
              {{ chapterHeading(hit.title, hit.index, book?.name) }}
            </span>
            <span class="hit-snippet">
              <template v-for="(seg, si) in highlightParts(hit.snippet, searchQuery)" :key="si">
                <mark v-if="seg.hit">{{ seg.text }}</mark>
                <span v-else>{{ seg.text }}</span>
              </template>
            </span>
          </button>
        </div>
      </aside>

      <!-- 排版设置 -->
      <aside v-if="settingsOpen" class="settings">
        <div class="set-block">
          <div class="set-label">阅读模式</div>
          <div class="font-row">
            <button
              type="button"
              class="font-btn"
              :class="{ 'is-active': !pagedMode }"
              @click="pagedMode = false"
            >
              上下滚动
            </button>
            <button
              type="button"
              class="font-btn"
              :class="{ 'is-active': pagedMode }"
              @click="pagedMode = true"
            >
              左右翻页
            </button>
          </div>
        </div>
        <div class="set-block">
          <div class="set-label">字号 <span class="val">{{ fontSize }}px</span></div>
          <input v-model.number="fontSize" type="range" min="14" max="28" step="1" />
        </div>
        <div class="set-block">
          <div class="set-label">行距 <span class="val">{{ lineHeight }}</span></div>
          <input v-model.number="lineHeight" type="range" min="1.4" max="2.2" step="0.1" />
        </div>
        <div class="set-block">
          <div class="set-label">字体</div>
          <div class="font-row">
            <button
              v-for="opt in fontOptions"
              :key="opt.value"
              type="button"
              class="font-btn"
              :class="{ 'is-active': readerFont === opt.value }"
              :style="{ fontFamily: opt.stack }"
              @click="readerFont = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
        <div class="set-block">
          <div class="set-label">内容宽度 <span class="val">{{ contentWidth }}px</span></div>
          <input v-model.number="contentWidth" type="range" min="560" max="1000" step="20" />
        </div>
        <div class="set-block">
          <div class="set-label">背景</div>
          <div class="theme-row">
            <button
              type="button"
              class="theme-swatch paper"
              :class="{ 'is-active': readerTheme === 'paper' }"
              title="纸白"
              @click="readerTheme = 'paper'"
            />
            <button
              type="button"
              class="theme-swatch warm"
              :class="{ 'is-active': readerTheme === 'warm' }"
              title="暖黄"
              @click="readerTheme = 'warm'"
            />
            <button
              type="button"
              class="theme-swatch night"
              :class="{ 'is-active': readerTheme === 'night' }"
              title="夜间"
              @click="readerTheme = 'night'"
            />
          </div>
        </div>
        <div class="set-block">
          <label class="autohide-row">
            <input v-model="autoHideTopbar" type="checkbox" />
            <span>阅读时自动隐藏顶栏（H 键切换）</span>
          </label>
        </div>
      </aside>
    </div>

  </div>
</template>

<style scoped>
.reader-root {
  height: 100%;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  color: var(--color-text);
}

.reader-top {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 12px;
  border-bottom: 1px solid var(--reader-border, var(--color-border));
  background: var(--color-surface);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  overflow: hidden;
  transition:
    height 180ms ease,
    opacity 180ms ease,
    border-color 180ms ease;
}

/* 沉浸模式：高度归零收起，内容自然上移 */
.reader-top.is-hidden {
  height: 0;
  opacity: 0;
  border-bottom-color: transparent;
  pointer-events: none;
}

/* 章节名相对视口水平居中（左右栏不等宽也不偏） */
.top-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  top: 0;
  height: 52px;
  display: flex;
  align-items: center;
  max-width: 32vw;
  pointer-events: none;
  z-index: 1;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.top-title {
  min-width: 0;
}

.name-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.top-title .name {
  font-size: var(--text-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 28vw;
}

.progress-text {
  flex-shrink: 0;
  font-size: var(--text-xs);
  white-space: nowrap;
}

.chapter-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 42vw;
  margin: 0 auto;
}

.top-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  flex: 0 0 auto;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-2);
  cursor: pointer;
}

.icon-btn:hover,
.icon-btn.is-on {
  background: var(--color-surface-2);
  color: var(--color-accent);
}

.reader-body {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

.toc {
  width: 260px;
  flex-shrink: 0;
  overflow: hidden;
  transition: width var(--duration, 160ms) ease;
}

/* 收起：宽度归零，仍留在 flex 流中，再点可完整恢复 */
.toc.is-closed {
  width: 0;
  border-right: none;
  opacity: 0;
  pointer-events: none;
}

.toc:not(.is-closed) {
  opacity: 1;
}

.content {
  flex: 1;
  min-width: 0;
}

.settings {
  flex-shrink: 0;
}

/* 窄屏：目录覆盖抽屉 */
.reader-body.is-narrow .toc.is-drawer {
  display: block;
  position: fixed;
  left: 0;
  top: 52px;
  bottom: 0;
  width: min(280px, 86vw);
  z-index: 30;
  box-shadow: var(--shadow-lg);
  opacity: 1;
  pointer-events: auto;
}

.reader-body.is-narrow .toc.is-drawer.is-closed {
  width: min(280px, 86vw);
  transform: translateX(-105%);
  opacity: 1;
  pointer-events: none;
}

.toc-mask {
  position: fixed;
  inset: 52px 0 0 0;
  background: var(--color-overlay);
  z-index: 20;
}

.toc,
.settings {
  border-right: 1px solid var(--reader-border, var(--color-border));
  background: var(--color-surface);
  overflow: auto;
  min-height: 0;
}

.settings {
  border-right: none;
  border-left: 1px solid var(--reader-border, var(--color-border));
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* ---- 书内搜索浮层 ---- */
.search-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  width: min(420px, calc(100vw - 24px));
  max-height: calc(100% - 24px);
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--reader-border, var(--color-border));
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 40;
  overflow: hidden;
}

.search-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid var(--reader-border, var(--color-border));
}

.search-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--reader-border, var(--color-border));
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--reader-fg, var(--color-text));
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
}

.search-input:focus {
  border-color: var(--color-accent);
}

.search-btn {
  height: 32px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.search-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.search-meta {
  padding: 8px 12px 0;
}

.search-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: auto;
  padding: 8px;
}

.search-hit {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--reader-fg, var(--color-text));
  text-align: left;
  font-family: inherit;
  cursor: pointer;
}

.search-hit:hover {
  background: var(--color-surface-2);
}

.hit-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hit-snippet {
  font-size: var(--text-xs);
  line-height: 1.5;
  color: var(--reader-muted, var(--color-text-2));
  word-break: break-word;
}

.hit-snippet mark {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  border-radius: 2px;
  padding: 0 1px;
}

.toc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--reader-border, var(--color-border));
}

.icon-btn.sm {
  width: 28px;
  height: 28px;
}

.toc-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border-bottom: 1px solid var(--reader-border, var(--color-border));
}

.toc-search-input {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--reader-border, var(--color-border));
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--reader-fg, var(--color-text));
  font-size: var(--text-xs);
  font-family: inherit;
  outline: none;
}

.toc-search-input:focus {
  border-color: var(--color-accent);
}

.toc-clear {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-3);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.toc-clear:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
}

.toc-count {
  margin-left: auto;
  margin-right: 4px;
  font-variant-numeric: tabular-nums;
}

.toc-list {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toc-item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-2);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.toc-item:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
}

.toc-item.is-active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-weight: 600;
}

.toc-item .idx {
  font-size: var(--text-xs);
  color: var(--color-text-3);
  min-width: 28px;
  font-variant-numeric: tabular-nums;
}

.toc-item .title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toc-empty {
  padding: 16px;
  text-align: center;
}

.content {
  overflow: auto;
  min-width: 0;
  padding: var(--space-6) var(--space-5);
}

/* ---- 左右翻页模式：多栏排版 + 横向平移 ---- */
.content-paged {
  overflow: hidden;
}

.paged-track.is-paged {
  width: 100%;
  max-width: var(--paged-width, 720px);
  height: 100%;
  margin: 0 auto;
}

.article.is-paged {
  height: 100%;
  width: 100%;
  max-width: none;
  margin: 0;
  column-fill: auto;
}

/* 分栏测量与渲染需要真实布局，不能跳过离屏段落 */
.article.is-paged .para {
  content-visibility: visible;
}

.article {
  max-width: 720px;
  margin: 0 auto;
}

.chapter-title {
  font-size: 1.45em;
  font-weight: 650;
  margin: 0 0 1.2em;
  letter-spacing: -0.01em;
}

.placeholder-body p {
  margin: 0 0 1em;
}

.chapter-body .para {
  margin: 0 0 1em;
  text-indent: 2em;
  line-height: inherit;
  /* 超长章节：离屏段落跳过渲染，降低长章卡顿 */
  content-visibility: auto;
  contain-intrinsic-size: 0 1.6em;
}

.demo-line {
  margin: 0 0 1em;
  color: var(--color-text-2);
}

/* 阅读主题 */
.theme-paper {
  --reader-bg: #f7f5f0;
  --reader-fg: #2a2a28;
  --reader-muted: #7a7770;
  --reader-border: #e2ddd2;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-paper .reader-top,
.theme-paper .toc,
.theme-paper .settings,
.theme-paper .search-panel {
  background: #f0eee8;
  color: var(--reader-fg);
}

.theme-paper .muted-xs,
.theme-paper .muted {
  color: var(--reader-muted);
}

.theme-warm {
  --reader-bg: #f3e7d3;
  --reader-fg: #3b2f22;
  --reader-muted: #8a7460;
  --reader-border: #e0cfae;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-warm .reader-top,
.theme-warm .toc,
.theme-warm .settings,
.theme-warm .search-panel {
  background: #ead9bc;
  color: var(--reader-fg);
}

.theme-night {
  --reader-bg: #12161c;
  --reader-fg: #c9d1d9;
  --reader-muted: #7d8794;
  --reader-border: #2a3240;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-night .reader-top,
.theme-night .toc,
.theme-night .settings,
.theme-night .search-panel {
  background: #171c24;
  color: var(--reader-fg);
  border-color: #2a3240;
}

.set-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.set-label {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--color-text-2);
}

.set-label .val {
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
}

.set-block input[type="range"] {
  width: 100%;
  accent-color: var(--color-accent);
}

.font-row {
  display: flex;
  gap: 6px;
}

.font-btn {
  flex: 1;
  height: 30px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-xs);
  cursor: pointer;
}

.font-btn.is-active {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.autohide-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-xs);
  color: var(--color-text-2);
  cursor: pointer;
}

.autohide-row input {
  accent-color: var(--color-accent);
}

.theme-row {
  display: flex;
  gap: 8px;
}

.theme-swatch {
  width: 36px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  cursor: pointer;
}

.theme-swatch.paper {
  background: #f7f5f0;
  border-color: var(--color-border);
}

.theme-swatch.warm {
  background: #f3e7d3;
  border-color: var(--color-border);
}

.theme-swatch.night {
  background: #12161c;
  border-color: var(--color-border);
}

.theme-swatch.is-active {
  border-color: var(--color-accent);
}

/* 章末导航：贴在正文末尾，随内容滚动 */
.chapter-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px 28px;
  flex-wrap: wrap;
  margin-top: 2.5em;
  padding-top: 1.25em;
  border-top: 1px solid var(--reader-border, var(--color-border));
}

.foot-btn {
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: var(--text-sm);
  font-weight: 500;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  min-width: 72px;
}

.foot-btn:hover:not(:disabled) {
  background: var(--color-surface-2);
  color: var(--color-accent);
}

.foot-btn:disabled {
  color: var(--color-text-3);
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 900px) {
  /* 中窄屏隐藏居中章节名，避免与左右工具重叠 */
  .top-center {
    display: none;
  }
}

@media (max-width: 900px) {
  /* 窄屏：正文占满；目录/排版为浮层 */
  .toc {
    display: none;
  }

  .settings {
    position: fixed;
    top: 52px;
    right: 0;
    bottom: 40px;
    width: min(280px, 86vw);
    z-index: 30;
    box-shadow: var(--shadow-lg);
    border-left: 1px solid var(--color-border);
  }
}
</style>
