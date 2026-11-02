<script setup lang="ts">
/** 阅读器排版设置 */
import { FONT_OPTIONS } from "@/views/reader/constants";
import type { ReaderFont, ReaderTheme } from "@/views/reader/constants";

defineProps<{
  pagedMode: boolean;
  fontSize: number;
  lineHeight: number;
  readerFont: ReaderFont;
  contentWidth: number;
  readerTheme: ReaderTheme;
  autoHideTopbar: boolean;
}>();

const emit = defineEmits<{
  (e: "update:pagedMode", value: boolean): void;
  (e: "update:fontSize", value: number): void;
  (e: "update:lineHeight", value: number): void;
  (e: "update:readerFont", value: ReaderFont): void;
  (e: "update:contentWidth", value: number): void;
  (e: "update:readerTheme", value: ReaderTheme): void;
  (e: "update:autoHideTopbar", value: boolean): void;
}>();

function num(e: Event): number {
  return Number((e.target as HTMLInputElement).value);
}

function checked(e: Event): boolean {
  return (e.target as HTMLInputElement).checked;
}
</script>

<template>
  <aside class="settings">
    <div class="set-block">
      <div class="set-label">阅读模式</div>
      <div class="font-row">
        <button
          type="button"
          class="font-btn"
          :class="{ 'is-active': !pagedMode }"
          @click="emit('update:pagedMode', false)"
        >
          上下滚动
        </button>
        <button
          type="button"
          class="font-btn"
          :class="{ 'is-active': pagedMode }"
          @click="emit('update:pagedMode', true)"
        >
          左右翻页
        </button>
      </div>
    </div>

    <div class="set-block">
      <div class="set-label">字号 <span class="val">{{ fontSize }}px</span></div>
      <input
        :value="fontSize"
        type="range"
        min="14"
        max="28"
        step="1"
        @input="emit('update:fontSize', num($event))"
      />
    </div>

    <div class="set-block">
      <div class="set-label">行距 <span class="val">{{ lineHeight }}</span></div>
      <input
        :value="lineHeight"
        type="range"
        min="1.4"
        max="2.2"
        step="0.1"
        @input="emit('update:lineHeight', num($event))"
      />
    </div>

    <div class="set-block">
      <div class="set-label">字体</div>
      <div class="font-row">
        <button
          v-for="opt in FONT_OPTIONS"
          :key="opt.value"
          type="button"
          class="font-btn"
          :class="{ 'is-active': readerFont === opt.value }"
          :style="{ fontFamily: opt.stack }"
          @click="emit('update:readerFont', opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>

    <div class="set-block">
      <div class="set-label">内容宽度 <span class="val">{{ contentWidth }}px</span></div>
      <input
        :value="contentWidth"
        type="range"
        min="560"
        max="1000"
        step="20"
        @input="emit('update:contentWidth', num($event))"
      />
    </div>

    <div class="set-block">
      <div class="set-label">背景</div>
      <div class="theme-row">
        <button
          type="button"
          class="theme-swatch paper"
          :class="{ 'is-active': readerTheme === 'paper' }"
          title="纸白"
          @click="emit('update:readerTheme', 'paper')"
        />
        <button
          type="button"
          class="theme-swatch warm"
          :class="{ 'is-active': readerTheme === 'warm' }"
          title="暖黄"
          @click="emit('update:readerTheme', 'warm')"
        />
        <button
          type="button"
          class="theme-swatch night"
          :class="{ 'is-active': readerTheme === 'night' }"
          title="夜间"
          @click="emit('update:readerTheme', 'night')"
        />
      </div>
    </div>

    <div class="set-block">
      <label class="autohide-row">
        <input
          :checked="autoHideTopbar"
          type="checkbox"
          @change="emit('update:autoHideTopbar', checked($event))"
        />
        <span>阅读时自动隐藏顶栏（H 键切换）</span>
      </label>
    </div>

    <div class="set-block">
      <div class="set-label">快捷键</div>
      <p class="muted-xs short-keys">
        ←/→ 翻页 · 空格 翻页 · T 目录 · H 顶栏 · F 全屏 · +/- 字号 · ? 帮助
      </p>
    </div>
  </aside>
</template>

<style scoped>
.settings {
  flex-shrink: 0;
  min-height: 0;
  overflow: auto;
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  border-left: 1px solid var(--reader-border, var(--color-border));
  background: var(--reader-panel-bg, var(--color-surface));
  color: var(--reader-fg, var(--color-text));
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
  color: var(--reader-muted, var(--color-text-2));
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

.short-keys {
  margin: 0;
  line-height: 1.6;
  color: var(--reader-muted, var(--color-text-3));
}

@media (max-width: 900px) {
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
