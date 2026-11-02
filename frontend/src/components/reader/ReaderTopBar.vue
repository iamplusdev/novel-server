<script setup lang="ts">
/** 阅读器顶栏：书名、章节、进度、同步状态与工具按钮 */
import AppIcon from "@/components/AppIcon.vue";
import type { ReaderSyncState } from "@/views/reader/constants";

defineProps<{
  bookName: string;
  progressText: string;
  chapterTitle: string;
  hidden: boolean;
  tocOpen: boolean;
  searchOpen: boolean;
  settingsOpen: boolean;
  syncState: ReaderSyncState;
}>();

const emit = defineEmits<{
  (e: "back"): void;
  (e: "toggle-toc"): void;
  (e: "toggle-search"): void;
  (e: "toggle-settings"): void;
  (e: "fullscreen"): void;
  (e: "apply-remote"): void;
}>();
</script>

<template>
  <header class="reader-top" :class="{ 'is-hidden': hidden }">
    <div class="top-left">
      <button type="button" class="icon-btn" title="返回" @click="emit('back')">
        <AppIcon name="back" :size="18" />
      </button>
      <div class="top-title">
        <div class="name-line">
          <span class="name">{{ bookName || "阅读" }}</span>
          <span v-if="progressText" class="progress-text muted-xs">{{ progressText }}</span>
          <span v-if="syncState === 'syncing'" class="sync-state">同步中…</span>
          <span v-else-if="syncState === 'failed'" class="sync-state is-error">同步失败</span>
          <button
            v-else-if="syncState === 'remote_newer'"
            type="button"
            class="sync-state is-link"
            @click="emit('apply-remote')"
          >
            远端有新进度
          </button>
          <span v-else-if="syncState === 'synced'" class="sync-state">已同步</span>
        </div>
      </div>
    </div>

    <div class="top-center">
      <div class="chapter-name">{{ chapterTitle }}</div>
    </div>

    <div class="top-actions">
      <button
        type="button"
        class="icon-btn"
        :class="{ 'is-on': tocOpen }"
        title="目录（T）"
        @click="emit('toggle-toc')"
      >
        <AppIcon name="list" :size="18" />
      </button>
      <button
        type="button"
        class="icon-btn"
        :class="{ 'is-on': searchOpen }"
        title="书内搜索（Ctrl+F）"
        @click="emit('toggle-search')"
      >
        <AppIcon name="search" :size="18" />
      </button>
      <button
        type="button"
        class="icon-btn"
        :class="{ 'is-on': settingsOpen }"
        title="排版"
        @click="emit('toggle-settings')"
      >
        <AppIcon name="type" :size="18" />
      </button>
      <button type="button" class="icon-btn" title="全屏（F）" @click="emit('fullscreen')">
        <AppIcon name="full" :size="18" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.reader-top {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 12px;
  border-bottom: 1px solid var(--reader-border, var(--color-border));
  background: var(--reader-panel-bg, var(--color-surface));
  color: var(--reader-fg, var(--color-text));
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  overflow: hidden;
  transition:
    height 180ms ease,
    opacity 180ms ease,
    border-color 180ms ease;
}

.reader-top.is-hidden {
  height: 0;
  opacity: 0;
  border-bottom-color: transparent;
  pointer-events: none;
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
  color: var(--reader-muted, var(--color-text-3));
  white-space: nowrap;
}

.sync-state {
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--reader-muted, var(--color-text-3));
  white-space: nowrap;
}

.sync-state.is-error {
  color: var(--color-danger);
}

.sync-state.is-link {
  border: none;
  border-radius: var(--radius-full);
  padding: 1px 8px;
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
}

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

.chapter-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--reader-fg, var(--color-text));
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

@media (max-width: 900px) {
  .top-center {
    display: none;
  }
}
</style>
