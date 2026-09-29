<script setup lang="ts">
/**
 * 网页阅读器：目录 / 正文 / 字号 / 行距 / 背景 / 进度 / 全屏。
 * 正文与完整目录走公开 API；进度写回管理端。
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  fetchBook,
  fetchBookChapters,
  fetchChapterContent,
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
const tocOpen = ref(true);
const settingsOpen = ref(false);
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

const chapters = computed(() => {
  if (tocItems.value.length) return tocItems.value;
  return (book.value?.chapters_preview || []).map((c) => ({
    id: c.id,
    index: c.index,
    title: c.title,
  }));
});
const activeChapter = computed(
  () => chapters.value.find((c) => c.id === activeChapterId.value) || chapters.value[0] || null,
);

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

/** 按当前章节序号换算阅读进度百分比 0–100 */
const readPercent = computed(() => {
  const list = chapters.value;
  const ch = activeChapter.value;
  if (!list.length || !ch) return Number(book.value?.read_percent ?? 0) || 0;
  const idx = list.findIndex((c) => c.id === ch.id);
  if (idx < 0) return 0;
  return Math.min(100, Math.round(((idx + 1) / list.length) * 100));
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
    // 完整目录（公开 API 分页拉取，小说通常一页够用）
    try {
      const toc = await fetchBookChapters(bookId.value, 1, 500);
      tocItems.value = (toc.items || []).map((c) => ({
        id: c.id,
        index: c.index,
        title: c.title || c.name || "",
      }));
    } catch {
      tocItems.value = (book.value?.chapters_preview || []).map((c) => ({
        id: c.id,
        index: c.index,
        title: c.title,
      }));
    }
    const list = chapters.value;
    // 优先续读：有 read_chapter_index 则定位到对应章节
    const savedIdx = book.value?.read_chapter_index ?? -1;
    if (list.length) {
      const byIndex = savedIdx >= 0 ? list.find((c) => c.index === savedIdx) : null;
      activeChapterId.value = (byIndex || list[0]!).id;
      await loadChapterContent(activeChapterId.value);
    }
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
}

watch([fontSize, lineHeight, readerTheme], persistPrefs);
// 切换章节后同步进度百分比并加载正文
watch(activeChapterId, (id) => {
  void persistProgress();
  if (id) void loadChapterContent(id);
});

function goChapter(id: number) {
  activeChapterId.value = id;
  contentEl.value?.scrollTo({ top: 0, behavior: "smooth" });
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
  }
}

onMounted(() => {
  void load();
  window.addEventListener("keydown", onKeydown);
  if (window.innerWidth < 900) tocOpen.value = false;
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  // 离开阅读器时落盘一次进度
  void persistProgress();
});
</script>

<template>
  <div class="reader-root" :class="themeClass">
    <header class="reader-top">
      <button type="button" class="icon-btn" title="返回详情" @click="router.back()">
        <AppIcon name="back" :size="18" />
      </button>
      <div class="top-title">
        <div class="name">{{ book?.name || "阅读" }}</div>
        <div class="sub muted-xs">{{ activeChapter?.title || "选择章节" }}</div>
      </div>
      <div class="top-actions">
        <button
          type="button"
          class="icon-btn"
          :class="{ 'is-on': tocOpen }"
          title="目录"
          @click="tocOpen = !tocOpen"
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

    <div class="reader-body">
      <!-- 目录 -->
      <aside v-if="tocOpen" class="toc">
        <div class="toc-head">目录</div>
        <div class="toc-list">
          <button
            v-for="ch in chapters"
            :key="ch.id"
            type="button"
            class="toc-item"
            :class="{ 'is-active': ch.id === activeChapter?.id }"
            @click="goChapter(ch.id)"
          >
            <span class="idx">{{ ch.index }}</span>
            <span class="title">{{ ch.title }}</span>
          </button>
          <p v-if="!chapters.length" class="muted toc-empty">暂无目录</p>
        </div>
      </aside>

      <!-- 正文区 -->
      <main ref="contentEl" class="content" :style="readerStyle">
        <article class="article">
          <h1 class="chapter-title">{{ activeChapter?.title || "开始阅读" }}</h1>
          <div v-if="contentLoading" class="placeholder-body muted">正文加载中…</div>
          <div v-else-if="chapterError" class="placeholder-body muted">{{ chapterError }}</div>
          <div v-else-if="chapterText" class="chapter-body">
            <p v-for="(para, i) in chapterText.split(/\n+/)" :key="i" class="para">{{ para }}</p>
          </div>
          <div v-else class="placeholder-body muted">
            <p>选择左侧目录开始阅读。</p>
          </div>
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

    <footer class="reader-foot">
      <span class="muted-xs">进度</span>
      <div class="progress-track">
        <div
          class="progress-bar"
          :class="{ 'is-success': readPercent >= 100 }"
          :style="{ width: readPercent + '%' }"
        />
      </div>
      <span class="muted-xs progress-label">{{ readPercent }}%</span>
    </footer>
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

.top-title {
  flex: 1;
  min-width: 0;
}

.top-title .name {
  font-size: var(--text-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.top-actions {
  display: flex;
  gap: 4px;
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
  display: grid;
  grid-template-columns: 260px 1fr 220px;
  min-height: 0;
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
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--color-border);
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

.reader-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
}

.progress-track {
  flex: 1;
  height: 4px;
  border-radius: var(--radius-full);
  background: var(--color-surface-3);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  width: 0;
  background: var(--color-accent);
}

@media (max-width: 900px) {
  .reader-body {
    grid-template-columns: 1fr;
  }

  .toc,
  .settings {
    display: none;
  }

  .reader-body:has(.toc) {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  /* 窄屏：目录/设置以浮层形式仍占一列时简化为单列，保留按钮切换后的显示 */
  .reader-root:has(.toc) .reader-body,
  .reader-root:has(.settings) .reader-body {
    grid-template-columns: 1fr;
  }

  .toc,
  .settings {
    position: fixed;
    top: 52px;
    bottom: 40px;
    width: min(280px, 86vw);
    z-index: 20;
    box-shadow: var(--shadow-lg);
    display: block;
  }

  .toc {
    left: 0;
  }

  .settings {
    right: 0;
    border-left: 1px solid var(--color-border);
  }
}
</style>
