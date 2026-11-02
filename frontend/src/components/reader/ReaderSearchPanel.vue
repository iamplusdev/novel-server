<script setup lang="ts">
/** 阅读器书内搜索面板 */
import { onMounted, ref } from "vue";
import { chapterHeading } from "@/api/admin";
import type { BookSearchHit } from "@/api/admin";
import { highlightParts } from "@/utils/highlight";

defineProps<{
  query: string;
  hits: BookSearchHit[];
  total: number;
  loading: boolean;
  error: string;
  bookName: string;
}>();

const emit = defineEmits<{
  (e: "update:query", value: string): void;
  (e: "search"): void;
  (e: "close"): void;
  (e: "select", hit: BookSearchHit): void;
}>();

const inputEl = ref<HTMLInputElement | null>(null);

onMounted(() => inputEl.value?.focus());

function onInput(e: Event) {
  emit("update:query", (e.target as HTMLInputElement).value);
}
</script>

<template>
  <aside class="search-panel" aria-label="书内搜索">
    <div class="search-head">
      <input
        ref="inputEl"
        :value="query"
        type="search"
        class="search-input"
        placeholder="在本书中搜索…"
        @input="onInput"
        @keyup.enter="emit('search')"
      />
      <button type="button" class="search-btn" :disabled="loading" @click="emit('search')">
        {{ loading ? "搜索中" : "搜索" }}
      </button>
      <button type="button" class="icon-btn sm" title="关闭" @click="emit('close')">
        ×
      </button>
    </div>

    <div class="search-meta muted-xs">
      <span v-if="loading">正在扫描正文…</span>
      <span v-else-if="query.trim() && hits.length">共 {{ total }} 处匹配</span>
      <span v-else-if="error">{{ error }}</span>
      <span v-else>回车开始搜索</span>
    </div>

    <div class="search-list">
      <button
        v-for="(hit, i) in hits"
        :key="`${hit.chapter_id}-${i}`"
        type="button"
        class="search-hit"
        @click="emit('select', hit)"
      >
        <span class="hit-title">
          {{ chapterHeading(hit.title, hit.index, bookName) }}
        </span>
        <span class="hit-snippet">
          <template v-for="(seg, si) in highlightParts(hit.snippet, query)" :key="si">
            <mark v-if="seg.hit">{{ seg.text }}</mark>
            <span v-else>{{ seg.text }}</span>
          </template>
        </span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.search-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  width: min(420px, calc(100vw - 24px));
  max-height: calc(100% - 24px);
  display: flex;
  flex-direction: column;
  background: var(--reader-panel-bg, var(--color-surface));
  color: var(--reader-fg, var(--color-text));
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

.icon-btn:hover {
  background: var(--color-surface-2);
  color: var(--color-accent);
}

.icon-btn.sm {
  width: 28px;
  height: 28px;
}

.search-meta {
  padding: 8px 12px 0;
  color: var(--reader-muted, var(--color-text-3));
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
</style>
