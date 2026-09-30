<script setup lang="ts">
/**
 * 独立全屏阅读页（不嵌管理后台）：目录可收缩 / 正文 / 排版 / 进度。
 * 正文与完整目录走公开 API；进度写回管理端。
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  chapterHeading,
  fetchAllBookChapters,
  fetchBook,
  fetchChapterContent,
  isTocPlaceholder,
  updateReadProgress,
} from "@/api/admin";
import AppIcon from "@/components/AppIcon.vue";
import type { BookDetail } from "@/api/types";

interface TocItem {
  id: number;
  index: number;
  title: string;
}

type ReaderTheme = "paper" | "warm" | "night";

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
/** 窄屏：目录以覆盖抽屉展示 */
const isNarrow = ref(window.innerWidth < 900);
const isFullscreen = ref(false);
const activeChapterId = ref<number | null>(null);

const fontSize = ref(Number(localStorage.getItem("novel_read_font") || 18));
const lineHeight = ref(Number(localStorage.getItem("novel_read_leading") || 1.8));
const readerTheme = ref<ReaderTheme>(
  (localStorage.getItem("novel_read_theme") as ReaderTheme) || "paper",
);

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

/** 顶栏进度文案：第 n / 总 · x% */
const progressText = computed(() => {
  const total = chapterTotal.value;
  const n = chapterNo.value;
  if (!total || !n) return "";
  return `第 ${n} / ${total} 章 · ${readPercent.value}%`;
});

const hasPrev = computed(() => chapterNo.value > 1);
const hasNext = computed(() => chapterNo.value > 0 && chapterNo.value < chapterTotal.value);

/** 拉取当前章节正文 */
async function loadChapterContent(chapterId: number) {
  if (!bookId.value || !chapterId) return;
  contentLoading.value = true;
  chapterError.value = "";
  try {
    const data = await fetchChapterContent(bookId.value, chapterId);
    chapterText.value = data.content || "";
    if (!chapterText.value) {
      chapterError.value = "本章正文为空";
    }
  } catch (e) {
    chapterText.value = "";
    chapterError.value = e instanceof Error ? e.message : "正文加载失败";
  } finally {
    contentLoading.value = false;
  }
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

    // 优先级：URL ?chapter= > 续读 read_chapter_index > 第一章
    const qChapter = Number.parseInt(String(route.query.chapter ?? ""), 10);
    let target = Number.isInteger(qChapter) && qChapter > 0
      ? list.find((c) => c.id === qChapter)
      : null;
    if (!target) {
      const savedIdx = book.value?.read_chapter_index ?? -1;
      target = savedIdx >= 0 ? list.find((c) => c.index === savedIdx) : null;
    }
    activeChapterId.value = (target || list[0]!).id;
    await loadChapterContent(activeChapterId.value);
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
  localStorage.setItem("novel_read_toc", tocOpen.value ? "1" : "0");
}

function toggleToc() {
  tocOpen.value = !tocOpen.value;
  localStorage.setItem("novel_read_toc", tocOpen.value ? "1" : "0");
}

function goBack() {
  // 优先回详情；无历史则回书库
  if (window.history.length > 1) router.back();
  else void router.push({ name: "library" });
}

watch([fontSize, lineHeight, readerTheme, tocOpen], persistPrefs);
// 切换章节后同步进度百分比并加载正文
watch(activeChapterId, (id) => {
  void persistProgress();
  if (id) void loadChapterContent(id);
});

function goChapter(id: number) {
  activeChapterId.value = id;
  // 窄屏选完章节后收起目录抽屉
  if (isNarrow.value) {
    tocOpen.value = false;
    localStorage.setItem("novel_read_toc", "0");
  }
  contentEl.value?.scrollTo({ top: 0, behavior: "smooth" });
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
  if (e.key === "Escape") {
    settingsOpen.value = false;
    // 窄屏 Esc 关掉目录抽屉
    if (isNarrow.value) tocOpen.value = false;
  }
}

function onResize() {
  isNarrow.value = window.innerWidth < 900;
}

onMounted(() => {
  void load();
  window.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", onResize);
  // 离开阅读器时落盘一次进度
  void persistProgress();
});
</script>

<template>
  <div class="reader-root" :class="themeClass">
    <header class="reader-top">
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
          title="目录（可收缩）"
          @click="toggleToc"
        >
          <AppIcon name="list" :size="18" />
        </button>
        <button
          type="button"
          class="icon-btn"
          :class="{ 'is-on': settingsOpen }"
          title="排版"
          @click="settingsOpen = !settingsOpen"
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
          <button type="button" class="icon-btn sm" title="收起目录" @click="toggleToc">
            <AppIcon name="back" :size="14" />
          </button>
        </div>
        <div class="toc-list">
          <button
            v-for="ch in displayChapters"
            :key="ch.id"
            type="button"
            class="toc-item"
            :class="{ 'is-active': ch.id === activeChapter?.id }"
            @click="goChapter(ch.id)"
          >
            <span class="idx">{{ ch.no }}</span>
            <span class="title">{{ ch.title }}</span>
          </button>
          <p v-if="!displayChapters.length" class="muted toc-empty">暂无目录</p>
        </div>
      </aside>
      <!-- 窄屏点遮罩关目录 -->
      <div
        v-if="isNarrow && tocOpen"
        class="toc-mask"
        @click="toggleToc"
      />

      <!-- 正文区 -->
      <main ref="contentEl" class="content" :style="readerStyle">
        <article class="article">
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
      </main>

      <!-- 排版设置 -->
      <aside v-if="settingsOpen" class="settings">
        <div class="set-block">
          <div class="set-label">字号 <span class="val">{{ fontSize }}px</span></div>
          <input v-model.number="fontSize" type="range" min="14" max="28" step="1" />
        </div>
        <div class="set-block">
          <div class="set-label">行距 <span class="val">{{ lineHeight }}</span></div>
          <input v-model.number="lineHeight" type="range" min="1.4" max="2.2" step="0.1" />
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
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  position: sticky;
  top: 0;
  z-index: 10;
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
  max-width: 42vw;
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
  border-right: 1px solid var(--color-border);
  background: var(--color-surface);
  overflow: auto;
  min-height: 0;
}

.settings {
  border-right: none;
  border-left: 1px solid var(--color-border);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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
  border-bottom: 1px solid var(--color-border);
}

.icon-btn.sm {
  width: 28px;
  height: 28px;
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
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-paper .reader-top,
.theme-paper .toc,
.theme-paper .settings {
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
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-warm .reader-top,
.theme-warm .toc,
.theme-warm .settings {
  background: #ead9bc;
  color: var(--reader-fg);
}

.theme-night {
  --reader-bg: #12161c;
  --reader-fg: #c9d1d9;
  --reader-muted: #7d8794;
  background: var(--reader-bg);
  color: var(--reader-fg);
}

.theme-night .reader-top,
.theme-night .toc,
.theme-night .settings {
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
  border-top: 1px solid var(--color-border);
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
