<script setup lang="ts">
/** 阅读统计：基于每本书最近一次阅读进度，不包含逐日阅读历史 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { fetchReadingStats } from "@/api/admin";
import type { BookListItem, ReadingStats } from "@/api/types";
import AppIcon from "@/components/AppIcon.vue";
import BaseEmpty from "@/components/BaseEmpty.vue";

const router = useRouter();
const stats = ref<ReadingStats | null>(null);
const loading = ref(false);
const error = ref("");

const readRatio = computed(() => {
  const s = stats.value;
  if (!s || !s.total_books) return 0;
  return Math.round((s.read_books * 100) / s.total_books);
});

const cards = computed(() => {
  const s = stats.value;
  if (!s) return [];
  return [
    { label: "总藏书", value: fmtNumber(s.total_books), unit: "本", tone: "default" },
    { label: "已读", value: fmtNumber(s.read_books), unit: "本", tone: "accent" },
    { label: "在读", value: fmtNumber(s.reading_books), unit: "本", tone: "warning" },
    { label: "已读完", value: fmtNumber(s.finished_books), unit: "本", tone: "success" },
    { label: "未读", value: fmtNumber(s.unread_books), unit: "本", tone: "muted" },
    {
      label: "估算已读",
      value: fmtWords(s.read_words),
      unit: "字",
      tone: "default",
      hint: "按阅读百分比估算",
    },
    {
      label: "平均进度",
      value: (s.avg_progress || 0).toFixed(1),
      unit: "%",
      tone: "accent",
    },
  ];
});

const maxCategory = computed(() =>
  Math.max(1, ...(stats.value?.by_category || []).map((c) => c.count)),
);

function fmtNumber(n?: number) {
  return Number(n || 0).toLocaleString("zh-CN");
}

function fmtWords(n?: number) {
  const value = Number(n || 0);
  if (value >= 100000000) return (value / 100000000).toFixed(1) + " 亿";
  if (value >= 10000) return (value / 10000).toFixed(1) + " 万";
  return fmtNumber(value);
}

function fmtTime(value: string) {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 16);
}

function readPercent(book: BookListItem) {
  return Math.max(0, Math.min(100, Math.round(Number(book.read_percent) || 0)));
}

function catWidth(count: number) {
  return Math.max(3, Math.round((count / maxCategory.value) * 100));
}

function openBook(id: number) {
  void router.push({ name: "book-detail", params: { id: String(id) } });
}

function onCoverError(e: Event) {
  (e.target as HTMLImageElement).style.visibility = "hidden";
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    stats.value = await fetchReadingStats();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载阅读统计失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div v-loading="loading" class="page stats-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">阅读统计</h1>
        <p class="muted-xs stats-subtitle">按每本书最近一次阅读进度估算，不含逐日阅读时长</p>
      </div>
      <div class="page-actions">
        <span class="count-pill">已读 {{ readRatio }}%</span>
        <button type="button" class="ghost-btn" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="14" />
          刷新
        </button>
      </div>
    </header>

    <div v-if="error" class="page-card stats-error">
      <p class="muted">{{ error }}</p>
      <button type="button" class="ghost-btn" @click="load">重试</button>
    </div>

    <template v-else-if="stats">
      <div class="stat-grid">
        <div
          v-for="card in cards"
          :key="card.label"
          class="stat-card"
          :class="`tone-${card.tone}`"
        >
          <div class="stat-value">
            {{ card.value }}<span class="stat-unit">{{ card.unit }}</span>
          </div>
          <div class="stat-label">{{ card.label }}</div>
          <div v-if="card.hint" class="stat-hint muted-xs">{{ card.hint }}</div>
        </div>
      </div>

      <section class="page-card">
        <div class="section-head">
          <h2 class="section-title">最近阅读</h2>
          <span class="muted-xs">{{ stats.recent.length }} 本</span>
        </div>
        <BaseEmpty
          v-if="!stats.recent.length"
          icon="book"
          title="还没有阅读记录"
          description="打开一本书开始阅读后，这里会显示最近进度。"
          action-text="去书库"
          @action="router.push({ name: 'library' })"
        />
        <div v-else class="recent-list">
          <button
            v-for="book in stats.recent"
            :key="book.id"
            type="button"
            class="recent-item"
            @click="openBook(book.id)"
          >
            <div class="recent-cover">
              <img
                v-if="book.cover_thumb_url"
                :src="book.cover_thumb_url"
                :alt="book.name"
                loading="lazy"
                decoding="async"
                @error="onCoverError"
              />
              <span v-else class="cover-fallback">{{ book.name.slice(0, 1) }}</span>
            </div>
            <div class="recent-main">
              <div class="recent-title" :title="book.name">{{ book.name }}</div>
              <div class="muted-xs recent-sub">
                {{ book.author || "佚名" }} · {{ book.category || "未分类" }}
              </div>
              <div class="recent-progress">
                <div
                  class="recent-progress-bar"
                  :style="{ width: `${readPercent(book)}%` }"
                />
              </div>
            </div>
            <div class="recent-meta">
              <span class="recent-percent">{{ readPercent(book) }}%</span>
              <span class="muted-xs">{{ fmtTime(book.read_at || "") }}</span>
            </div>
          </button>
        </div>
      </section>

      <section v-if="stats.by_category.length" class="page-card">
        <div class="section-head">
          <h2 class="section-title">已读分类</h2>
          <span class="muted-xs">按已读书数量</span>
        </div>
        <div class="cat-list">
          <div v-for="cat in stats.by_category" :key="cat.name" class="cat-row">
            <span class="cat-name" :title="cat.name">{{ cat.name }}</span>
            <div class="cat-track">
              <div class="cat-bar" :style="{ width: `${catWidth(cat.count)}%` }" />
            </div>
            <span class="cat-count">{{ cat.count }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.stats-subtitle {
  margin: 4px 0 0;
}

.stats-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.stats-error p {
  margin: 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.stat-card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-unit {
  margin-left: 3px;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-3);
}

.stat-label {
  margin-top: 4px;
  font-size: var(--text-sm);
  color: var(--color-text-2);
}

.stat-hint {
  margin-top: 2px;
}

.tone-accent .stat-value {
  color: var(--color-accent);
}

.tone-success .stat-value {
  color: var(--color-success);
}

.tone-warning .stat-value {
  color: var(--color-warning);
}

.tone-muted .stat-value {
  color: var(--color-text-3);
}

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: var(--space-3);
}

.section-head .section-title {
  margin: 0;
}

.recent-list {
  display: flex;
  flex-direction: column;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 8px;
  border: none;
  border-bottom: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
}

.recent-item:last-child {
  border-bottom: none;
}

.recent-item:hover {
  background: var(--color-surface-2);
}

.recent-cover {
  width: 44px;
  height: 60px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-accent-soft);
}

.recent-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--color-accent);
  font-size: var(--text-lg);
  font-weight: 650;
}

.recent-main {
  flex: 1;
  min-width: 0;
}

.recent-title {
  font-size: var(--text-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-sub {
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-progress {
  height: 4px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
}

.recent-progress-bar {
  height: 100%;
  border-radius: inherit;
  background: var(--color-accent);
}

.recent-meta {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}

.recent-percent {
  color: var(--color-accent);
  font-size: var(--text-sm);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.cat-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.cat-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) 36px;
  align-items: center;
  gap: 10px;
}

.cat-name {
  font-size: var(--text-sm);
  color: var(--color-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cat-track {
  height: 8px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
}

.cat-bar {
  height: 100%;
  border-radius: inherit;
  background: var(--color-accent);
}

.cat-count {
  color: var(--color-text-3);
  font-size: var(--text-xs);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.count-pill {
  padding: 2px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-xs);
}

@media (max-width: 900px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 576px) {
  .cat-row {
    grid-template-columns: 80px minmax(0, 1fr) 30px;
  }

  .recent-cover {
    width: 38px;
    height: 52px;
  }

  .recent-meta .muted-xs {
    display: none;
  }
}
</style>
