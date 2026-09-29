<script setup lang="ts">
/**
 * 书库封面墙：书源/分类筛选、搜索、排序、视图切换、多选批量、分页。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { SOURCE_OPTS, useLibraryStore } from "@/stores/library";
import { batchDeleteBooks } from "@/api/admin";
import { startBatchScrape } from "@/api/progress";
import BookCard from "@/components/BookCard.vue";
import AppIcon from "@/components/AppIcon.vue";

const router = useRouter();
const lib = useLibraryStore();

const searchInput = ref(lib.q);
const coverWidth = ref(Number(localStorage.getItem("novel_grid_size") || 150));
const viewMode = ref<"grid" | "list">(
  (localStorage.getItem("novel_view_mode") as "grid" | "list") || "grid",
);
const selectedIds = ref<Set<number>>(new Set());
const showSkeleton = ref(true);
const batchBusy = ref(false);
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const sourceLabels: Record<string, string> = {
  "": "全部",
  起点: "起点",
  番茄: "番茄",
  纵横: "纵横",
};

const sortOptions = [
  { value: "updated", label: "导入/更新时间" },
  { value: "title", label: "书名" },
  { value: "author", label: "作者" },
  { value: "words", label: "字数" },
  { value: "chapters", label: "章节" },
];

const gridStyle = computed(() => {
  if (viewMode.value === "list") {
    return { gridTemplateColumns: "1fr" };
  }
  return {
    gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${coverWidth.value}px), 1fr))`,
  };
});

const selectedCount = computed(() => selectedIds.value.size);

/** 按封面宽度估算列数×可见行数，动态每页数量（保证正整数） */
function computePageSize(): number {
  const wrap = gridWrapRef.value;
  const gap = 14;
  const width = wrap?.clientWidth || 960;
  const coverW = Math.floor(Number(coverWidth.value) || 150);
  const cols = Math.max(2, Math.floor((width + gap) / (coverW + gap)));
  const coverH = (coverW * 4) / 3 + 72;
  const viewH = window.innerHeight - 220;
  const rows = Math.max(1, Math.floor((viewH + gap) / (coverH + gap)));
  const n = cols * rows;
  if (!Number.isFinite(n)) return 24;
  return Math.min(200, Math.max(Math.floor(n), 8));
}

const gridWrapRef = ref<HTMLElement | null>(null);

function applyPageSize() {
  const next = computePageSize();
  if (next === lib.pageSize) return;
  const firstIndex = (lib.page - 1) * lib.pageSize;
  lib.pageSize = next;
  lib.page = Math.floor(firstIndex / next) + 1;
  void lib.loadBooks();
}

function onGridSize() {
  localStorage.setItem("novel_grid_size", String(coverWidth.value));
  applyPageSize();
}

function onViewModeChange(mode: "grid" | "list") {
  viewMode.value = mode;
  localStorage.setItem("novel_view_mode", mode);
}

function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    void lib.applyFilter({ q: searchInput.value.trim() });
  }, 300);
}

function onSourceClick(src: string) {
  void lib.applyFilter({ source: src });
}

function onCategoryClick(cat: string) {
  void lib.applyFilter({ category: cat });
}

function onSortChange(val: string) {
  void lib.applyFilter({ sort: val });
}

function onToggleUnscraped() {
  void lib.applyFilter({ onlyUnscraped: !lib.onlyUnscraped });
}

function openBook(id: number) {
  router.push({ name: "book-detail", params: { id: String(id) } });
}

function toggleSelect(id: number) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
}

function selectAllOnPage() {
  const next = new Set(selectedIds.value);
  for (const b of lib.items) next.add(b.id);
  selectedIds.value = next;
}

function clearSelection() {
  selectedIds.value = new Set();
}

/** 批量删除：危险操作二次确认 */
async function onBatchDelete() {
  const ids = [...selectedIds.value];
  if (!ids.length || batchBusy.value) return;
  try {
    await ElMessageBox.confirm(
      `将删除已选 ${ids.length} 本书（含封面与本地库记录，不删源 TXT），确认？`,
      "批量删除",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  batchBusy.value = true;
  try {
    const res = await batchDeleteBooks(ids);
    ElMessage.success(`已删除 ${res.deleted_count} 本`);
    clearSelection();
    await Promise.all([lib.loadBooks(), lib.loadStats()]);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "批量删除失败");
  } finally {
    batchBusy.value = false;
  }
}

/** 对已选书发起批量刮削（跳到体检页可看进度） */
async function onBatchScrape() {
  const ids = [...selectedIds.value];
  if (!ids.length || batchBusy.value) return;
  try {
    await ElMessageBox.confirm(
      `对已选 ${ids.length} 本执行刮削？可在「体检 → 刮削」查看进度。`,
      "批量刮削",
      { type: "info", confirmButtonText: "开始刮削", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  batchBusy.value = true;
  try {
    const res = await startBatchScrape({
      source: "all",
      only_missing: false,
      min_score: 0.8,
      book_ids: ids,
    });
    if (res.started) {
      ElMessage.success("刮削任务已启动");
      clearSelection();
      router.push({ name: "check", query: { tab: "scrape" } });
    } else {
      ElMessage.warning("已有刮削任务在运行，请稍后再试");
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "启动刮削失败");
  } finally {
    batchBusy.value = false;
  }
}

onMounted(async () => {
  applyPageSize();
  showSkeleton.value = true;
  await Promise.all([lib.loadStats(), lib.loadBooks()]);
  showSkeleton.value = false;
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
});

let resizeTimer: ReturnType<typeof setTimeout> | undefined;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(applyPageSize, 200);
}
</script>

<template>
  <div class="page library-page">
    <header class="page-header">
      <div class="title-row">
        <h1 class="page-title">书库</h1>
        <span class="count-pill">{{ lib.total }} 本</span>
      </div>
      <div class="page-actions">
        <div class="search-box">
          <AppIcon name="search" :size="16" />
          <input
            v-model="searchInput"
            type="search"
            class="search-input"
            placeholder="搜索书名 / 作者 / 标签…"
            @input="onSearchInput"
            @keyup.enter="void lib.applyFilter({ q: searchInput.trim() })"
          />
        </div>

        <select
          class="sort-select"
          :value="lib.sort"
          aria-label="排序"
          @change="onSortChange(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="opt in sortOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>

        <div class="view-toggle" role="group" aria-label="视图">
          <button
            type="button"
            class="toggle-btn"
            :class="{ 'is-active': viewMode === 'grid' }"
            title="网格"
            @click="onViewModeChange('grid')"
          >
            <AppIcon name="grid" :size="16" />
          </button>
          <button
            type="button"
            class="toggle-btn"
            :class="{ 'is-active': viewMode === 'list' }"
            title="列表"
            @click="onViewModeChange('list')"
          >
            <AppIcon name="list" :size="16" />
          </button>
        </div>

        <div v-if="viewMode === 'grid'" class="size-ctrl">
          <span class="muted-xs">大小</span>
          <input
            v-model.number="coverWidth"
            type="range"
            min="110"
            max="240"
            step="10"
            class="size-slider"
            aria-label="封面大小"
            @change="onGridSize"
          />
        </div>
      </div>
    </header>

    <div class="filter-bar">
      <div class="chip-row" role="tablist" aria-label="书源筛选">
        <button
          v-for="src in SOURCE_OPTS"
          :key="src"
          type="button"
          class="chip"
          :class="{ 'is-active': lib.source === src }"
          @click="onSourceClick(src)"
        >
          {{ sourceLabels[src] || src || "全部" }}
        </button>
        <span class="divider" />
        <button
          type="button"
          class="chip"
          :class="{ 'is-active': lib.onlyUnscraped }"
          @click="onToggleUnscraped"
        >
          仅未刮削
        </button>
      </div>

      <div class="chip-row" role="tablist" aria-label="分类筛选">
        <button
          type="button"
          class="chip"
          :class="{ 'is-active': !lib.category }"
          @click="onCategoryClick('')"
        >
          全部分类
        </button>
        <button
          v-for="cat in lib.categoryNames"
          :key="cat"
          type="button"
          class="chip"
          :class="{ 'is-active': lib.category === cat }"
          @click="onCategoryClick(cat)"
        >
          {{ cat }}
        </button>
      </div>
    </div>

    <!-- 批量操作条 -->
    <div v-if="selectedCount" class="batch-bar">
      <span>已选 <strong>{{ selectedCount }}</strong> 本</span>
      <div class="batch-actions">
        <button type="button" class="ghost-btn" @click="selectAllOnPage">全选本页</button>
        <button type="button" class="ghost-btn" @click="clearSelection">取消选择</button>
        <button
          type="button"
          class="primary-btn"
          :disabled="batchBusy"
          @click="onBatchScrape"
        >
          批量刮削
        </button>
        <button
          type="button"
          class="ghost-btn danger"
          :disabled="batchBusy"
          @click="onBatchDelete"
        >
          批量删除
        </button>
      </div>
    </div>

    <!-- 骨架屏 -->
    <div
      v-if="showSkeleton && lib.loading"
      class="grid-wrap"
      :style="gridStyle"
      aria-hidden="true"
    >
      <div v-for="i in 8" :key="i" class="skel-card">
        <div class="skeleton skel-cover" />
        <div class="skeleton skel-line" />
        <div class="skeleton skel-line short" />
      </div>
    </div>

    <div
      v-else
      v-loading="lib.loading"
      ref="gridWrapRef"
      class="grid-wrap"
      :style="gridStyle"
    >
      <div v-if="!lib.loading && !lib.items.length" class="empty-state">
        <div class="empty-icon">
          <AppIcon name="book" :size="28" />
        </div>
        <h3>书库还是空的</h3>
        <p class="muted">到「导入」页扫描本地 TXT，即可开始管理你的小说。</p>
        <button type="button" class="primary-btn" @click="router.push({ name: 'import' })">
          去导入
        </button>
      </div>

      <BookCard
        v-for="b in lib.items"
        :key="b.id"
        :book="b"
        :view="viewMode"
        selectable
        :selected="selectedIds.has(b.id)"
        @open="openBook"
        @toggle-select="toggleSelect"
      />
    </div>

    <div class="pager">
      <button
        type="button"
        class="ghost-btn"
        :disabled="lib.page <= 1"
        @click="void lib.gotoPage(lib.page - 1)"
      >
        上一页
      </button>
      <span class="page-indicator muted">
        {{ lib.page }} / {{ Math.max(lib.totalPages, 1) }}
      </span>
      <button
        type="button"
        class="ghost-btn"
        :disabled="lib.page >= lib.totalPages"
        @click="void lib.gotoPage(lib.page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.count-pill {
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-xs);
  border: 1px solid var(--color-border);
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  min-width: 220px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-3);
}

.search-box:focus-within {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
  color: var(--color-accent);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
  min-width: 0;
}

.search-input::placeholder {
  color: var(--color-text-3);
}

.sort-select {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.view-toggle {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  gap: 2px;
}

.toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-3);
  cursor: pointer;
}

.toggle-btn.is-active {
  background: var(--color-surface);
  color: var(--color-accent);
  box-shadow: var(--shadow-sm);
}

.size-ctrl {
  display: flex;
  align-items: center;
  gap: 8px;
}

.size-slider {
  width: 96px;
  accent-color: var(--color-accent);
}

.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.divider {
  width: 1px;
  height: 18px;
  background: var(--color-border);
  margin: 0 4px;
}

.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--color-accent-soft);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  font-size: var(--text-sm);
}

.batch-actions {
  display: flex;
  gap: 8px;
}

.grid-wrap {
  display: grid;
  gap: 14px;
  min-height: 200px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow-x: hidden;
  align-content: start;
}

.skel-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skel-cover {
  aspect-ratio: 3 / 4;
  border-radius: var(--radius-md);
}

.skel-line {
  height: 12px;
  border-radius: 4px;
}

.skel-line.short {
  width: 60%;
}

.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: var(--space-7) var(--space-4);
  text-align: center;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.empty-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  color: var(--color-text-3);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}

.empty-state h3 {
  margin: 0;
  font-size: var(--text-lg);
}

.primary-btn {
  margin-top: 8px;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}

.primary-btn:hover {
  background: var(--color-accent-hover);
}

.ghost-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.ghost-btn:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0 16px;
}

.page-indicator {
  min-width: 64px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .search-box {
    min-width: 0;
    flex: 1;
  }

  .size-ctrl {
    display: none;
  }

  /* 工具条纵向堆叠，筛选可横向滚动 */
  .page-actions {
    width: 100%;
  }

  .filter-bar {
    overflow-x: auto;
  }

  .chip-row {
    flex-wrap: nowrap;
    padding-bottom: 4px;
  }

  .batch-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .batch-actions {
    width: 100%;
  }

  .batch-actions .ghost-btn,
  .batch-actions .primary-btn {
    flex: 1;
  }
}
</style>
