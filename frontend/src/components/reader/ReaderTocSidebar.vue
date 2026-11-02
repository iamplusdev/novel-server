<script setup lang="ts">
/** 阅读器目录：筛选、当前章定位、窄屏抽屉 */
import { computed, nextTick, ref, watch } from "vue";
import { isTocPlaceholder } from "@/api/admin";
import AppIcon from "@/components/AppIcon.vue";

interface TocItem {
  id: number;
  index: number;
  title: string;
}

const props = defineProps<{
  items: TocItem[];
  bookName: string;
  activeChapterId: number | null;
  open: boolean;
  narrow: boolean;
  filter: string;
}>();

const emit = defineEmits<{
  (e: "update:filter", value: string): void;
  (e: "select", id: number): void;
  (e: "toggle"): void;
}>();

const displayItems = computed(() =>
  props.items
    .filter((c) => !isTocPlaceholder(c.title, props.bookName))
    .map((c, i) => ({ ...c, no: i + 1 })),
);

const filteredItems = computed(() => {
  const kw = props.filter.trim().toLowerCase();
  if (!kw) return displayItems.value;
  return displayItems.value.filter(
    (c) => c.title.toLowerCase().includes(kw) || String(c.no) === kw,
  );
});

const listEl = ref<HTMLElement | null>(null);

/** 打开目录或切章时把当前章滚到列表中间 */
function scrollActiveIntoView() {
  if (!props.open || !props.activeChapterId) return;
  void nextTick(() => {
    const list = listEl.value;
    const el = list?.querySelector<HTMLElement>(
      `[data-chapter-id="${props.activeChapterId}"]`,
    );
    if (!list || !el) return;
    const listRect = list.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const delta = elRect.top - listRect.top - list.clientHeight / 2 + el.clientHeight / 2;
    list.scrollTo({ top: Math.max(0, list.scrollTop + delta), behavior: "auto" });
  });
}

watch(
  () => [props.open, props.activeChapterId, props.filter],
  scrollActiveIntoView,
  { immediate: true },
);

function onFilterInput(e: Event) {
  emit("update:filter", (e.target as HTMLInputElement).value);
}
</script>

<template>
  <aside class="toc" :class="{ 'is-drawer': narrow, 'is-closed': !open }">
    <div class="toc-head">
      <span>目录</span>
      <span v-if="filter" class="toc-count muted-xs">
        {{ filteredItems.length }}/{{ displayItems.length }}
      </span>
      <button type="button" class="icon-btn sm" title="收起目录" @click="emit('toggle')">
        <AppIcon name="back" :size="14" />
      </button>
    </div>

    <div class="toc-search">
      <input
        :value="filter"
        type="search"
        class="toc-search-input"
        placeholder="筛选章节…"
        @input="onFilterInput"
      />
      <button
        v-if="filter"
        type="button"
        class="toc-clear"
        title="清除筛选"
        @click="emit('update:filter', '')"
      >
        ×
      </button>
    </div>

    <div ref="listEl" class="toc-list">
      <button
        v-for="ch in filteredItems"
        :key="ch.id"
        type="button"
        class="toc-item"
        :data-chapter-id="ch.id"
        :class="{ 'is-active': ch.id === activeChapterId }"
        @click="emit('select', ch.id)"
      >
        <span class="idx">{{ ch.no }}</span>
        <span class="title">{{ ch.title }}</span>
      </button>
      <p v-if="!filteredItems.length" class="muted toc-empty">
        {{ filter ? "无匹配章节" : "暂无目录" }}
      </p>
    </div>
  </aside>
</template>

<style scoped>
.toc {
  width: 260px;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--reader-border, var(--color-border));
  background: var(--reader-panel-bg, var(--color-surface));
  color: var(--reader-fg, var(--color-text));
  transition: width var(--duration, 160ms) ease;
}

.toc.is-closed {
  width: 0;
  border-right: none;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}

.toc:not(.is-closed) {
  opacity: 1;
}

.toc.is-drawer {
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

.toc.is-drawer.is-closed {
  width: min(280px, 86vw);
  transform: translateX(-105%);
  opacity: 1;
  pointer-events: none;
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

.toc-count {
  margin-left: auto;
  margin-right: 4px;
  color: var(--reader-muted, var(--color-text-3));
  font-variant-numeric: tabular-nums;
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

.toc-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
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
  color: var(--reader-fg, var(--color-text));
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.toc-item:hover {
  background: var(--color-surface-2);
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
  color: var(--reader-muted, var(--color-text-2));
}
</style>
