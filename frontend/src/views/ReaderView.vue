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
  pullBookProgress,
  searchBookContent,
  updateReadProgress,
} from "@/api/admin";
import ReaderHelpPanel from "@/components/reader/ReaderHelpPanel.vue";
import ReaderSearchPanel from "@/components/reader/ReaderSearchPanel.vue";
import ReaderSettingsPanel from "@/components/reader/ReaderSettingsPanel.vue";
import ReaderTocSidebar from "@/components/reader/ReaderTocSidebar.vue";
import ReaderTopBar from "@/components/reader/ReaderTopBar.vue";
import { FONT_STACKS } from "@/views/reader/constants";
import type {
  ReaderFont,
  ReaderSyncState,
  ReaderTheme,
} from "@/views/reader/constants";
import { highlightParts } from "@/utils/highlight";
import type { BookSearchHit, PullProgressResult } from "@/api/admin";
import type { BookDetail } from "@/api/types";

interface TocItem {
  id: number;
  index: number;
  title: string;
}

const route = useRoute();
const router = useRouter();

const book = ref<BookDetail | null>(null);
const loading = ref(false);
const contentLoading = ref(false);
const chapterText = ref("");
const chapterError = ref("");

/** 正文段落及其在原文中的起始偏移（搜索/远端位置跳转用） */
const chapterParagraphs = computed(() => {
  const text = chapterText.value || "";
  const out: { text: string; start: number }[] = [];
  const re = /[^\n]+/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) {
    out.push({ text: match[0], start: match.index });
  }
  return out;
});
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
/** 搜索命中跳转：目标章节 + 字内偏移 + 关键词（用于高亮） */
const pendingSearchJump = ref<{ chapterId: number; offset: number; query: string } | null>(null);
const activeHighlightQuery = ref("");
/** Beacon 推送节流：pagehide 与 visibilitychange 可能连续触发 */
let lastBeaconAt = 0;

/** 快捷键帮助浮层 */
const helpOpen = ref(false);
/** 当前章内滚动比例（0–1），用于整体进度条 */
const scrollFraction = ref(0);

/** WebDAV 同步状态：超时不再阻塞阅读，晚到的远端进度给出手动入口 */
const syncState = ref<ReaderSyncState>("idle");
const lateRemote = ref<PullProgressResult | null>(null);
let syncStateTimer: ReturnType<typeof setTimeout> | undefined;

function setSyncState(state: ReaderSyncState) {
  syncState.value = state;
  clearTimeout(syncStateTimer);
  if (state === "synced" || state === "failed") {
    syncStateTimer = setTimeout(() => {
      if (syncState.value === state) syncState.value = "idle";
    }, 4000);
  }
}

/** 首次进入翻页模式的交互提示（只提示一次） */
const pagedHint = ref(false);
let pagedHintTimer: ReturnType<typeof setTimeout> | undefined;

function maybeShowPagedHint() {
  if (localStorage.getItem("novel_read_paged_hint") === "1") return;
  localStorage.setItem("novel_read_paged_hint", "1");
  pagedHint.value = true;
  clearTimeout(pagedHintTimer);
  pagedHintTimer = setTimeout(() => {
    pagedHint.value = false;
  }, 6000);
}

const bookId = computed(() => {
  const raw = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id;
  const n = Number.parseInt(String(raw ?? ""), 10);
  return Number.isInteger(n) && n > 0 ? n : 0;
});

const chapters = computed(() => tocItems.value);
/** 目录筛选关键词（标题或章节号） */
const tocFilter = ref("");
const activeChapter = computed(
  () => chapters.value.find((c) => c.id === activeChapterId.value) || chapters.value[0] || null,
);
const activeChapterTitle = computed(() =>
  activeChapter.value
    ? chapterHeading(activeChapter.value.title, activeChapter.value.index, book.value?.name)
    : "选择章节",
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
  return `第 ${n} / ${total} 章 · ${overallPercent.value}%${pageInfo}`;
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
  // 章内滚动占比（整体进度条展示用）
  const max = Math.max(
    0,
    (contentEl.value?.scrollHeight || 0) - (contentEl.value?.clientHeight || 0),
  );
  scrollFraction.value = max > 0 ? Math.min(1, Math.max(0, top / max)) : 1;

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

  // 远端进度/搜索命中位置只对目标章节生效一次；搜索优先
  let remotePos: number | null = null;
  if (pendingRemotePos.value?.chapterId === chapterId) {
    remotePos = pendingRemotePos.value.pos;
    pendingRemotePos.value = null;
  }
  let searchJump: { offset: number; query: string } | null = null;
  if (pendingSearchJump.value?.chapterId === chapterId) {
    searchJump = {
      offset: pendingSearchJump.value.offset,
      query: pendingSearchJump.value.query,
    };
    pendingSearchJump.value = null;
    activeHighlightQuery.value = searchJump.query;
  }

  if (pagedMode.value) {
    await relayoutPaged();
    if (seq !== contentSeq) return;
    const wantLast = pendingLastPageFor === chapterId;
    if (wantLast) pendingLastPageFor = null;
    const ratio = searchJump
      ? searchJump.offset / Math.max(1, chapterText.value.length)
      : remotePos != null
        ? remotePos / Math.max(1, chapterText.value.length)
        : -1;
    const desired = wantLast
      ? pageCount.value - 1
      : ratio >= 0
        ? Math.round(ratio * Math.max(0, pageCount.value - 1))
        : savedPageFor(chapterId);
    pageIndex.value = Math.max(0, Math.min(desired, pageCount.value - 1));
    return;
  }

  if (!contentEl.value) return;
  await nextTick();
  if (seq !== contentSeq) return;
  const top = searchJump
    ? scrollTopForChar(searchJump.offset)
    : remotePos != null
      ? scrollTopForChar(remotePos)
      : savedTopFor(chapterId);
  // 程序化滚动不触发顶栏显示/隐藏
  scrollSuppressed = true;
  contentEl.value.scrollTo({ top, behavior: "auto" });
  lastScrollTop = top;
  requestAnimationFrame(() => {
    scrollSuppressed = false;
  });
}

/** 把章内字符位置映射为所在段落的滚动位置（段落 start 保留换行偏移） */
function scrollTopForChar(charPos: number): number {
  const el = contentEl.value;
  if (!el || charPos <= 0) return 0;
  const paras = chapterParagraphs.value;
  let idx = paras.findIndex((p) => charPos >= p.start && charPos < p.start + p.text.length);
  if (idx < 0) idx = paras.findIndex((p) => p.start >= charPos);
  if (idx < 0) idx = paras.length - 1;
  const node = el.querySelectorAll<HTMLElement>(".chapter-body .para")[idx];
  if (!node) return 0;
  const rect = node.getBoundingClientRect();
  const cRect = el.getBoundingClientRect();
  return Math.max(0, el.scrollTop + rect.top - cRect.top - 8);
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

/** 展示用整体进度：章节序号 + 章内滚动/页码占比 */
const overallPercent = computed(() => {
  const total = chapterTotal.value;
  const n = chapterNo.value;
  if (!total || !n) return Number(book.value?.read_percent ?? 0) || 0;
  const frac = pagedMode.value
    ? pageCount.value > 0
      ? (pageIndex.value + 1) / pageCount.value
      : 0
    : scrollFraction.value;
  return Math.min(100, Math.max(0, Math.round(((n - 1 + frac) / total) * 100)));
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
  const loadBookId = bookId.value;
  loading.value = true;
  pendingRemotePos.value = null;
  pendingSearchJump.value = null;
  activeHighlightQuery.value = "";
  lateRemote.value = null;
  setSyncState("syncing");

  // 与书籍/目录并行拉取；最多等 1.4 秒，超时后先按本地进度阅读
  const pullTask = pullBookProgress(loadBookId).then(
    (r) => (bookId.value === loadBookId ? r : null),
    () => {
      if (bookId.value === loadBookId) setSyncState("failed");
      return null;
    },
  );
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 1400));

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
    if (!list.length) {
      setSyncState("idle");
      return;
    }

    // 书籍/目录与进度拉取并行；到这里通常已有结果，最坏再等剩余时间
    const pulled = await Promise.race([pullTask, timeout]);
    if (pulled) {
      setSyncState(pulled.enabled ? "synced" : "idle");
    } else if (syncState.value !== "failed") {
      setSyncState("syncing");
      void pullTask.then((late) => {
        if (bookId.value !== loadBookId) return;
        if (!late) {
          setSyncState("failed");
          return;
        }
        if (!late.enabled) {
          setSyncState("idle");
          return;
        }
        if (late.updated && late.chapter_id) {
          lateRemote.value = late;
          setSyncState("remote_newer");
        } else {
          setSyncState("synced");
        }
      });
    }

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

/** 晚到的远端进度：用户点击后再切换，避免打断当前阅读 */
async function applyLateRemote() {
  const remote = lateRemote.value;
  if (!remote?.chapter_id) return;
  const target = chapters.value.find((c) => c.id === remote.chapter_id);
  lateRemote.value = null;
  if (!target) {
    setSyncState("idle");
    return;
  }
  if (typeof remote.chapter_pos === "number" && remote.chapter_pos > 0) {
    pendingRemotePos.value = { chapterId: target.id, pos: remote.chapter_pos };
  }
  setSyncState("synced");
  if (target.id === activeChapterId.value) {
    await loadChapterContent(target.id);
  } else {
    activeChapterId.value = target.id;
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
  if (
    !autoHideTopbar.value ||
    searchOpen.value ||
    settingsOpen.value ||
    tocOpen.value ||
    helpOpen.value
  )
    return;
  topbarTimer = setTimeout(() => {
    if (
      !autoHideTopbar.value ||
      searchOpen.value ||
      settingsOpen.value ||
      tocOpen.value ||
      helpOpen.value
    )
      return;
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
  if (settingsOpen.value) {
    helpOpen.value = false;
    revealTopbar();
  } else {
    scheduleTopbarHide();
  }
}

function openSearch() {
  searchOpen.value = true;
  settingsOpen.value = false;
  helpOpen.value = false;
  revealTopbar();
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

/** 对当前已加载章节执行搜索跳转（同章命中时） */
async function applySearchJump() {
  const jump = pendingSearchJump.value;
  if (!jump || jump.chapterId !== activeChapterId.value || !chapterText.value) return;
  pendingSearchJump.value = null;
  activeHighlightQuery.value = jump.query;
  await nextTick();
  if (!contentEl.value) return;
  if (pagedMode.value) {
    await relayoutPaged();
    const last = Math.max(0, pageCount.value - 1);
    pageIndex.value = Math.min(
      last,
      Math.max(0, Math.round((jump.offset / Math.max(1, chapterText.value.length)) * last)),
    );
    return;
  }
  const top = scrollTopForChar(jump.offset);
  scrollSuppressed = true;
  contentEl.value.scrollTo({ top, behavior: "auto" });
  lastScrollTop = top;
  requestAnimationFrame(() => {
    scrollSuppressed = false;
  });
}

function openSearchResult(hit: BookSearchHit) {
  pendingSearchJump.value = {
    chapterId: hit.chapter_id,
    offset: hit.offset,
    query: searchQuery.value.trim(),
  };
  searchOpen.value = false;
  if (hit.chapter_id === activeChapterId.value) {
    void applySearchJump();
  } else {
    goChapter(hit.chapter_id);
  }
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
  // 手动切章时清除高亮；若目标是搜索跳转章节，restore 会重新设置
  activeHighlightQuery.value = "";
  if (pendingSearchJump.value && pendingSearchJump.value.chapterId !== id) {
    pendingSearchJump.value = null;
  }
  pageIndex.value = 0;
  pageCount.value = 1;
  scrollFraction.value = 0;
  void persistProgress();
  void loadChapterContent(id);
});

// 切换阅读模式：翻页模式重新分页；滚动模式恢复该章滚动位置
watch(pagedMode, async (on) => {
  const id = activeChapterId.value;
  pendingLastPageFor = null;
  if (on) maybeShowPagedHint();
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
  pendingSearchJump.value = null;
  activeHighlightQuery.value = "";
  lateRemote.value = null;
  clearTimeout(syncStateTimer);
  syncState.value = "idle";
  pageIndex.value = 0;
  pageCount.value = 1;
  chapterCache.clear();
  prefetching.clear();
  void load();
});

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

/** 快捷键调整字号（14–28） */
function changeFont(delta: number) {
  fontSize.value = Math.min(28, Math.max(14, fontSize.value + delta));
}

/** PageUp / PageDown：翻页模式翻页，滚动模式翻一屏 */
function pageScroll(dir: 1 | -1) {
  if (pagedMode.value) {
    if (dir > 0) nextPage();
    else prevPage();
    return;
  }
  const el = contentEl.value;
  if (el) {
    el.scrollBy({ top: dir * el.clientHeight * 0.9, behavior: "smooth" });
  }
}

function toggleHelp() {
  helpOpen.value = !helpOpen.value;
  if (helpOpen.value) {
    searchOpen.value = false;
    settingsOpen.value = false;
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
    }
    helpOpen.value = false;
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
  } else if (e.key === "PageUp") {
    e.preventDefault();
    pageScroll(-1);
  } else if (e.key === "PageDown") {
    e.preventDefault();
    pageScroll(1);
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
  } else if (e.key.toLowerCase() === "f") {
    void toggleFullscreen();
  } else if (e.key === "+" || e.key === "=") {
    changeFont(1);
  } else if (e.key === "-") {
    changeFont(-1);
  } else if (e.key === "?") {
    toggleHelp();
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
  if (pagedMode.value) maybeShowPagedHint();
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
  clearTimeout(syncStateTimer);
  clearTimeout(pagedHintTimer);
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
    <ReaderTopBar
      :book-name="book?.name || ''"
      :progress-text="progressText"
      :chapter-title="activeChapterTitle"
      :hidden="topbarHidden"
      :toc-open="tocOpen"
      :search-open="searchOpen"
      :settings-open="settingsOpen"
      :sync-state="syncState"
      @back="goBack"
      @toggle-toc="toggleToc"
      @toggle-search="toggleSearch"
      @toggle-settings="toggleSettings"
      @fullscreen="toggleFullscreen"
      @apply-remote="applyLateRemote"
    />

    <div class="reader-body">
      <ReaderTocSidebar
        v-model:filter="tocFilter"
        :items="tocItems"
        :book-name="book?.name || ''"
        :active-chapter-id="activeChapterId"
        :open="tocOpen"
        :narrow="isNarrow"
        @select="goChapter"
        @toggle="toggleToc"
      />
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
            <p v-for="(para, i) in chapterParagraphs" :key="i" class="para">
              <template v-if="activeHighlightQuery">
                <template
                  v-for="(seg, si) in highlightParts(para.text, activeHighlightQuery)"
                  :key="si"
                >
                  <mark v-if="seg.hit" class="search-mark">{{ seg.text }}</mark>
                  <span v-else>{{ seg.text }}</span>
                </template>
              </template>
              <template v-else>{{ para.text }}</template>
            </p>
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

      <ReaderHelpPanel v-if="helpOpen" @close="helpOpen = false" />

      <ReaderSearchPanel
        v-if="searchOpen"
        v-model:query="searchQuery"
        :hits="searchHits"
        :total="searchTotal"
        :loading="searchLoading"
        :error="searchError"
        :book-name="book?.name || ''"
        @search="runSearch"
        @close="searchOpen = false"
        @select="openSearchResult"
      />

      <ReaderSettingsPanel
        v-if="settingsOpen"
        v-model:paged-mode="pagedMode"
        v-model:font-size="fontSize"
        v-model:line-height="lineHeight"
        v-model:reader-font="readerFont"
        v-model:content-width="contentWidth"
        v-model:reader-theme="readerTheme"
        v-model:auto-hide-topbar="autoHideTopbar"
      />
    </div>

    <!-- 首次进入翻页模式的交互提示 -->
    <div v-if="pagedHint" class="paged-hint">
      <span>点击正文左右区域或左右滑动翻页；章末继续翻进入下一章</span>
      <button type="button" @click="pagedHint = false">知道了</button>
    </div>

    <!-- 整体阅读进度条与翻页页码 -->
    <div class="reader-progress" :title="`进度 ${overallPercent}%`" aria-hidden="true">
      <div class="reader-progress-bar" :style="{ width: `${overallPercent}%` }" />
    </div>
    <div v-if="pagedMode" class="reader-page-indicator" aria-hidden="true">
      {{ pageIndex + 1 }} / {{ pageCount }}
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

.reader-body {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

.toc-mask {
  position: fixed;
  inset: 52px 0 0 0;
  background: var(--color-overlay);
  z-index: 20;
}

.content {
  flex: 1;
  min-width: 0;
  overflow: auto;
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

/* 书内搜索命中高亮 */
.search-mark {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  border-radius: 2px;
  padding: 0 1px;
}

/* ---- 整体进度与页码 ---- */
.reader-progress {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  z-index: 60;
  pointer-events: none;
  background: transparent;
}

.reader-progress-bar {
  height: 100%;
  background: var(--color-accent);
  transition: width 120ms linear;
}

.reader-page-indicator {
  position: fixed;
  right: 12px;
  bottom: 10px;
  z-index: 60;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  opacity: 0.85;
}

.paged-hint {
  position: fixed;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  z-index: 70;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: calc(100vw - 32px);
  padding: 8px 12px;
  border: 1px solid var(--reader-border, var(--color-border));
  border-radius: var(--radius-full);
  background: var(--reader-panel-bg, var(--color-surface));
  color: var(--color-text-2);
  box-shadow: var(--shadow-lg);
  font-size: var(--text-xs);
}

.paged-hint button {
  flex-shrink: 0;
  border: none;
  border-radius: var(--radius-full);
  padding: 2px 10px;
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
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

/* 阅读主题 */
.theme-paper {
  --reader-bg: #f7f5f0;
  --reader-fg: #2a2a28;
  --reader-muted: #7a7770;
  --reader-border: #e2ddd2;
  --reader-panel-bg: #f0eee8;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-warm {
  --reader-bg: #f3e7d3;
  --reader-fg: #3b2f22;
  --reader-muted: #8a7460;
  --reader-border: #e0cfae;
  --reader-panel-bg: #ead9bc;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-night {
  --reader-bg: #12161c;
  --reader-fg: #c9d1d9;
  --reader-muted: #7d8794;
  --reader-border: #2a3240;
  --reader-panel-bg: #171c24;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-paper .muted-xs,
.theme-paper .muted {
  color: var(--reader-muted);
}

.theme-warm .muted-xs,
.theme-warm .muted {
  color: var(--reader-muted);
}

.theme-night .muted-xs,
.theme-night .muted {
  color: var(--reader-muted);
}
</style>
