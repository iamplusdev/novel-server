<script setup lang="ts">
/**
 * 书库封面墙：书源/分类筛选、搜索、排序、分页。
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { SOURCE_OPTS, useLibraryStore } from "@/stores/library";

const router = useRouter();
const lib = useLibraryStore();

const searchInput = ref(lib.q);
const coverWidth = ref(Number(localStorage.getItem("novel_grid_size") || 150));
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

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fill, minmax(${coverWidth.value}px, 1fr))`,
}));

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
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

function onCoverError(e: Event) {
  const img = e.target as HTMLImageElement;
  img.style.visibility = "hidden";
}

function openBook(id: number) {
  router.push({ name: "book-detail", params: { id: String(id) } });
}

function onGridSize() {
  localStorage.setItem("novel_grid_size", String(coverWidth.value));
}

onMounted(async () => {
  await Promise.all([lib.loadStats(), lib.loadBooks()]);
});

watch(
  () => lib.page,
  () => {
    /* 分页由分页器触发 loadBooks */
  },
);
</script>

<template>
  <div class="library-page">
    <header class="toolbar">
      <div class="toolbar-left">
        <h2>书库</h2>
        <el-tag round type="info">{{ lib.total }}</el-tag>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchInput"
          placeholder="搜索书名 / 作者 / 标签…"
          clearable
          style="width: 220px"
          @input="onSearchInput"
          @clear="void lib.applyFilter({ q: '' })"
        />
        <el-select
          :model-value="lib.sort"
          style="width: 150px"
          @change="(v: string) => onSortChange(v)"
        >
          <el-option
            v-for="opt in sortOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <div class="size-ctrl">
          <span class="muted">大小</span>
          <el-slider
            v-model="coverWidth"
            :min="110"
            :max="240"
            :step="10"
            style="width: 100px"
            @change="onGridSize"
          />
        </div>
      </div>
    </header>

    <div class="chip-bar" role="tablist" aria-label="书源筛选">
      <el-check-tag
        v-for="src in SOURCE_OPTS"
        :key="src"
        :checked="lib.source === src"
        class="chip"
        @change="() => onSourceClick(src)"
      >
        {{ sourceLabels[src] || src || "全部" }}
      </el-check-tag>
    </div>

    <div class="chip-bar" role="tablist" aria-label="分类筛选">
      <el-check-tag
        :checked="!lib.category"
        class="chip"
        @change="() => onCategoryClick('')"
      >
        全部
      </el-check-tag>
      <el-check-tag
        v-for="cat in lib.categoryNames"
        :key="cat"
        :checked="lib.category === cat"
        class="chip"
        @change="() => onCategoryClick(cat)"
      >
        {{ cat }}
      </el-check-tag>
    </div>

    <div v-loading="lib.loading" class="grid-wrap" :style="gridStyle">
      <el-empty
        v-if="!lib.loading && !lib.items.length"
        description="暂无书籍，请到「导入」页导入 TXT。"
      />
      <article
        v-for="b in lib.items"
        :key="b.id"
        class="book-card"
        tabindex="0"
        role="link"
        @click="openBook(b.id)"
        @keyup.enter="openBook(b.id)"
      >
        <div class="book-cover">
          <img
            v-if="b.cover_url || b.cover_path"
            :src="b.cover_url || b.cover_path || ''"
            :alt="b.name"
            loading="lazy"
            decoding="async"
            @error="onCoverError"
          />
          <div v-else class="placeholder">{{ b.name }}</div>
        </div>
        <div class="book-meta">
          <div class="book-name" :title="b.name">{{ b.name }}</div>
          <div class="book-sub">
            <span>{{ b.author || "佚名" }}</span>
            <span v-if="b.status">{{ b.status }}</span>
          </div>
          <div class="book-sub muted">
            <span>{{ fmtWords(b.word_count) }}字</span>
            <span>{{ b.chapter_count ?? "—" }}章</span>
          </div>
        </div>
      </article>
    </div>

    <div class="pager">
      <el-button size="small" :disabled="lib.page <= 1" @click="void lib.gotoPage(lib.page - 1)">
        上一页
      </el-button>
      <span class="muted">{{ lib.page }} / {{ lib.totalPages }}</span>
      <el-button
        size="small"
        :disabled="lib.page >= lib.totalPages"
        @click="void lib.gotoPage(lib.page + 1)"
      >
        下一页
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.library-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-left h2 {
  margin: 0;
  font-size: 20px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.size-ctrl {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chip-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  cursor: pointer;
}

.grid-wrap {
  display: grid;
  gap: 14px;
  min-height: 200px;
}

.book-card {
  background: var(--el-bg-color);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.book-card:hover,
.book-card:focus {
  border-color: var(--el-color-primary);
  outline: none;
}

.book-cover {
  aspect-ratio: 3 / 4;
  background: var(--el-fill-color-light);
  overflow: hidden;
}

.book-cover img {
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
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 8px;
  text-align: center;
  word-break: break-all;
}

.book-meta {
  padding: 8px 10px 10px;
}

.book-name {
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.book-sub {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0 16px;
}
</style>
