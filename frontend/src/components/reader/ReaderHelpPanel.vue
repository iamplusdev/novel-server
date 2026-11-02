<script setup lang="ts">
/** 阅读器快捷键帮助 */
const emit = defineEmits<{ (e: "close"): void }>();
</script>

<template>
  <aside class="search-panel help-panel" aria-label="快捷键">
    <div class="search-head">
      <span class="help-title">快捷键</span>
      <button type="button" class="icon-btn sm" title="关闭" @click="emit('close')">
        ×
      </button>
    </div>
    <ul class="shortcut-list">
      <li><kbd>←</kbd><kbd>→</kbd><span>上一页/章 · 下一页/章</span></li>
      <li><kbd>空格</kbd><span>翻页 / 下翻一屏（Shift 反向）</span></li>
      <li><kbd>PageUp</kbd><kbd>PageDown</kbd><span>翻页 / 翻屏</span></li>
      <li><kbd>T</kbd><span>目录</span></li>
      <li><kbd>H</kbd><span>显示 / 隐藏顶栏</span></li>
      <li><kbd>F</kbd><span>全屏</span></li>
      <li><kbd>Ctrl/Cmd+F</kbd><span>书内搜索</span></li>
      <li><kbd>+</kbd><kbd>-</kbd><span>字号</span></li>
      <li><kbd>?</kbd><span>快捷键</span></li>
      <li><kbd>Esc</kbd><span>关闭浮层</span></li>
    </ul>
  </aside>
</template>

<style scoped>
.search-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  width: min(360px, calc(100vw - 24px));
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

.help-title {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 600;
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

.shortcut-list {
  list-style: none;
  margin: 0;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  font-size: var(--text-xs);
  color: var(--reader-muted, var(--color-text-2));
}

.shortcut-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.shortcut-list kbd {
  min-width: 24px;
  padding: 1px 5px;
  border: 1px solid var(--reader-border, var(--color-border));
  border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--color-surface-2);
  color: var(--color-text);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  text-align: center;
}

.shortcut-list span {
  margin-left: auto;
  color: var(--color-text-3);
}
</style>
