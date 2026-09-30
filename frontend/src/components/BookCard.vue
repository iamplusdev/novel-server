<script setup lang="ts">
/**
 * 书卡：网格 / 列表两种密度。
 * 刮削状态由 source_id / detail_url 派生；阅读进度仅 UI 位（暂无数据）。
 */
import { computed } from "vue";
import type { BookListItem } from "@/api/types";

const props = withDefaults(
  defineProps<{
    book: BookListItem;
    view?: "grid" | "list";
    selectable?: boolean;
    selected?: boolean;
    /** 网格封面宽度（px），用于小卡降级展示 */
    coverWidth?: number;
  }>(),
  {
    view: "grid",
    selectable: false,
    selected: false,
    coverWidth: 150,
  },
);

/** 尺寸档位：大/中/小，控制元信息密度（滑杆 120–220） */
const sizeTier = computed(() => {
  if (props.view === "list") return "lg";
  const w = Number(props.coverWidth) || 150;
  if (w >= 160) return "lg";
  if (w >= 130) return "md";
  return "sm";
});

const emit = defineEmits<{
  (e: "open", id: number): void;
  (e: "toggle-select", id: number): void;
}>();

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
}

/** 有站外 ID 或详情链接视为已刮削 */
function isScraped(b: BookListItem) {
  return Boolean(b.source_id || b.detail_url);
}

/** 阅读进度百分比（0–100），缺省视为 0 */
function readPercent(b: BookListItem) {
  const n = Number(b.read_percent ?? 0);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, Math.round(n)));
}

function progressLabel(b: BookListItem) {
  const p = readPercent(b);
  if (p <= 0) return "未读";
  if (p >= 100) return "已读完";
  return `已读 ${p}%`;
}

function onCoverError(e: Event) {
  const img = e.target as HTMLImageElement;
  img.style.visibility = "hidden";
}

function onClick() {
  if (props.selectable && props.selected) return;
  emit("open", props.book.id);
}

function onSelectClick(e: Event) {
  e.stopPropagation();
  emit("toggle-select", props.book.id);
}

function statusClass(status: string) {
  if (status === "完结") return "is-success";
  if (status === "连载") return "is-warning";
  return "";
}
</script>

<template>
  <article
    class="book-card"
    :class="[`is-${view}`, `size-${sizeTier}`, { 'is-selected': selected }]"
    tabindex="0"
    role="link"
    @click="onClick"
    @keyup.enter="onClick"
  >
    <div class="cover-wrap">
      <div class="cover">
        <img
          v-if="book.cover_url || book.cover_path"
          :src="book.cover_url || book.cover_path || ''"
          :alt="book.name"
          loading="lazy"
          decoding="async"
          @error="onCoverError"
        />
        <div v-else class="placeholder">{{ book.name }}</div>
      </div>

      <label v-if="selectable" class="select-box" @click.stop>
        <input
          type="checkbox"
          :checked="selected"
          @change="onSelectClick"
        />
      </label>

      <div class="status-float">
        <span
          class="status-dot"
          :class="isScraped(book) ? 'is-success' : 'is-info'"
          :title="isScraped(book) ? '已刮削' : '未刮削'"
        >
          {{ isScraped(book) ? "已刮削" : "未刮削" }}
        </span>
      </div>
    </div>

    <div class="meta">
      <div class="name" :title="book.name">{{ book.name }}</div>
      <div v-if="sizeTier !== 'sm'" class="sub">
        <span class="author" :title="book.author">{{ book.author || "佚名" }}</span>
        <span v-if="book.status" class="tag-soft" :class="statusClass(book.status)">
          {{ book.status }}
        </span>
      </div>

      <div v-if="sizeTier === 'lg' && book.tags?.length" class="tags">
        <span v-for="t in book.tags.slice(0, 3)" :key="t" class="tag-soft">{{ t }}</span>
        <span v-if="book.tags.length > 3" class="tag-soft">+{{ book.tags.length - 3 }}</span>
      </div>

      <!-- 阅读进度：大/中卡显示 -->
      <div v-if="sizeTier !== 'sm'" class="progress-slot" :title="progressLabel(book)">
        <div class="progress-track">
          <div
            class="progress-bar"
            :class="{ 'is-success': readPercent(book) >= 100 }"
            :style="{ width: readPercent(book) + '%' }"
          />
        </div>
        <span class="progress-text muted-xs">{{ progressLabel(book) }}</span>
      </div>

      <div v-if="sizeTier === 'lg'" class="stats muted-xs">
        <span>{{ fmtWords(book.word_count) }}字</span>
        <span>{{ book.chapter_count ?? "—" }}章</span>
      </div>
    </div>

    <!-- 列表模式：右侧简介，填补空白 -->
    <div v-if="view === 'list'" class="intro-block" :title="book.intro || ''">
      {{ book.intro || "暂无简介" }}
    </div>
  </article>
</template>

<style scoped>
.book-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  min-width: 0;
  max-width: 100%;
  transition:
    border-color var(--duration) ease,
    box-shadow var(--duration) ease,
    transform var(--duration) ease;
  position: relative;
}

.book-card:hover,
.book-card:focus-visible {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-md);
  outline: none;
}

.book-card.is-selected {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px var(--color-accent-ring);
}

/* ---- 列表模式：封面 | 基本信息 | 简介 ---- */
.book-card.is-list {
  display: grid;
  grid-template-columns: 72px minmax(120px, 0.85fr) minmax(0, 1.5fr);
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2);
}

.book-card.is-list .cover-wrap {
  width: 72px;
}

.book-card.is-list .cover {
  aspect-ratio: 3 / 4;
  width: 72px;
  border-radius: var(--radius-sm);
}

.book-card.is-list .status-float {
  display: none;
}

.book-card.is-list .meta {
  padding: 0;
  min-height: 0;
  gap: 4px;
}

.book-card.is-list .progress-slot {
  max-width: 220px;
}

/* 列表信息列较窄：隐藏标签行，高度更整齐 */
.book-card.is-list .tags {
  display: none;
}

/* 右侧简介：两行省略，填满剩余空白 */
.intro-block {
  font-size: var(--text-xs);
  color: var(--color-text-3);
  line-height: 1.55;
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.cover-wrap {
  position: relative;
}

.cover {
  aspect-ratio: 3 / 4;
  background: var(--color-surface-2);
  overflow: hidden;
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-3);
  font-size: var(--text-sm);
  padding: 8px;
  text-align: center;
  word-break: break-all;
  background:
    linear-gradient(160deg, var(--color-surface-2), var(--color-surface-3));
}

.select-box {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(15, 20, 28, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--duration) ease;
  z-index: 2;
}

.book-card:hover .select-box,
.book-card.is-selected .select-box {
  opacity: 1;
}

.select-box input {
  width: 14px;
  height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: var(--color-accent);
}

.status-float {
  position: absolute;
  left: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: rgba(15, 20, 28, 0.62);
  backdrop-filter: blur(6px);
  color: #e8edf5;
}

.status-float .status-dot {
  color: #e8edf5;
}

.meta {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  /* 元信息区高度固定，网格卡片对齐 */
  min-height: 118px;
  min-width: 0;
}

/* 中卡：隐藏标签/统计，书名可两行 */
.book-card.size-md .meta {
  min-height: 82px;
  padding: 8px 10px 10px;
  gap: 4px;
}

.book-card.size-md .name {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.35;
}

/* 小卡：仅书名一行省略 */
.book-card.size-sm .meta {
  min-height: 44px;
  padding: 6px 8px 8px;
  gap: 0;
}

.book-card.size-sm .name {
  font-size: 12px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.book-card.size-md .progress-text {
  display: none;
}

.meta .sub {
  min-height: 22px;
}

.meta .stats {
  margin-top: auto;
}

.name {
  font-weight: 600;
  font-size: var(--text-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text);
}

.sub {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.author {
  font-size: var(--text-xs);
  color: var(--color-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tags {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  overflow: hidden;
  white-space: nowrap;
  /* 标签只占一行，避免卡片高度不一对不齐 */
  height: 22px;
  align-items: center;
}

.tags .tag-soft {
  flex-shrink: 0;
  max-width: 7.5em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-slot {
  display: flex;
  align-items: center;
  gap: 8px;
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
  background: var(--color-accent);
  border-radius: inherit;
  transition: width var(--duration) ease;
}

.progress-bar.is-success {
  background: var(--color-success);
}

.progress-text {
  flex-shrink: 0;
}

.stats {
  display: flex;
  gap: 8px;
}

/* 窄屏强制紧凑（与书库移动端 100px 网格一致） */
@media (max-width: 768px) {
  .book-card.is-grid .meta {
    min-height: 48px;
    padding: 6px 8px 8px;
    gap: 4px;
  }

  .book-card.is-grid .name {
    font-size: 12px;
    line-height: 1.3;
  }

  .book-card.is-grid .tags,
  .book-card.is-grid .stats,
  .book-card.is-grid .progress-text {
    display: none;
  }

  .book-card.is-grid .sub {
    min-height: 0;
  }
}
</style>
