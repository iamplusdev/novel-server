<script setup lang="ts">
/**
 * 单本刮削弹窗：搜索 / 按书号拉详情 / 核对后写入。
 * emits: applied —— 写入成功后由父组件刷新表单
 */
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  SCRAPE_MODE_OPTS,
  SCRAPE_SOURCE_OPTS,
  cleanHintTags,
  looksLikeBookId,
  scrapeApply,
  scrapeDetail,
  scrapeSearch,
} from "@/api/scrape";
import type { BookDetail, ScrapeHit } from "@/api/types";
import AppIcon from "@/components/AppIcon.vue";

const props = defineProps<{
  visible: boolean;
  bookId: number | string;
  localName: string;
  localAuthor: string;
}>();

const emit = defineEmits<{
  (e: "update:visible", v: boolean): void;
  (e: "applied", detail: BookDetail): void;
}>();

const keyword = ref(props.localName || "");
const source = ref("qidian");
/** 刮削取数方式：auto / api / chrome（fnOS Chrome） */
const scrapeMode = ref("auto");
const loading = ref(false);
const applying = ref(false);
const tip = ref("将把结果写入当前编辑中的书籍。多条结果时请核对书名/作者后再点「采用」。");
const items = ref<ScrapeHit[]>([]);

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit("update:visible", v),
});

// 打开弹窗时自动填入书名（含标题后加载的情况）
watch(
  () => props.visible,
  (v) => {
    if (!v) return;
    const name = (props.localName || "").trim();
    if (name) keyword.value = name;
    items.value = [];
    tip.value = "将把结果写入当前编辑中的书籍。多条结果时请核对书名/作者后再点「采用」。";
  },
  { immediate: true },
);

function close() {
  dialogVisible.value = false;
}

async function runSearch() {
  const kw = keyword.value.trim();
  if (!kw) {
    ElMessage.warning("请填写书名或书号/链接");
    return;
  }
  loading.value = true;
  items.value = [];
  try {
    if (looksLikeBookId(kw)) {
      tip.value = "按书号拉取详情…";
      const hit = await scrapeDetail({
        source: source.value,
        source_book_id: kw,
        mode: scrapeMode.value,
      });
      items.value = [{ ...hit, source_id: hit.source_id || kw }];
    } else {
      tip.value = "正在搜索…";
      const res = await scrapeSearch({
        keyword: kw,
        source: source.value,
        limit: 10,
        mode: scrapeMode.value,
      });
      items.value = res.items || [];
      if (items.value.length) {
        tip.value = `找到 ${items.value.length} 条，请核对后点「采用并写入」`;
        ElMessage.success(`找到 ${items.value.length} 条，请核对后点「采用」`);
      } else {
        tip.value = "无匹配结果";
        ElMessage.warning("无匹配结果");
      }
    }
  } catch (e) {
    tip.value = e instanceof Error ? e.message : "搜索失败";
    ElMessage.error(tip.value);
  } finally {
    loading.value = false;
  }
}

async function askAndApply(hit: ScrapeHit) {
  if (!hit.source_id) return;
  const nameDiff = props.localName && hit.name && props.localName !== hit.name;
  const authorDiff = props.localAuthor && hit.author && props.localAuthor !== hit.author;
  const lines = [
    `本地：${props.localName || "—"}${props.localAuthor ? " · " + props.localAuthor : ""}`,
    `${hit.source || "站外"}：${hit.name || ""}${hit.author ? " · " + hit.author : ""}`,
    `ID ${hit.source_id || ""} · 来源 ${hit.source || "—"}`,
    hit.latest_chapter ? `最新：${hit.latest_chapter}` : "",
  ].filter(Boolean);
  if (nameDiff || authorDiff) {
    lines.push("书名或作者与本地不一致，请再次确认！");
  }
  try {
    await ElMessageBox.confirm(lines.join("\n"), "确认采用", {
      type: "warning",
      confirmButtonText: "写入数据库",
      cancelButtonText: "取消",
      customStyle: { whiteSpace: "pre-line" },
    });
  } catch {
    return;
  }
  await applyHit(hit);
}

/** 安全取正整数，避免 "NaN"/"undefined" 进请求体 */
function toPositiveInt(v: unknown): number {
  const n = Math.floor(Number(v));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

async function applyHit(hit: ScrapeHit) {
  const bookId = toPositiveInt(props.bookId);
  const srcId = String(hit.source_id ?? "").trim();
  if (!bookId) {
    ElMessage.error("无效的书籍 ID");
    return;
  }
  if (!srcId) {
    ElMessage.error("缺少站外书籍 ID，无法写入");
    return;
  }
  applying.value = true;
  tip.value = "正在拉取详情并写入…";
  try {
    const res = await scrapeApply(bookId, {
      source: source.value,
      source_book_id: srcId,
      mode: scrapeMode.value,
      with_cover: true,
      hint_name: hit.name || null,
      hint_author: hit.author || null,
      hint_intro: hit.intro || null,
      hint_status: hit.status || null,
      hint_cover_url: hit.cover_url || null,
      hint_tags: cleanHintTags(hit.tags),
      hint_word_count: toPositiveInt(hit.word_count),
      hint_category: hit.category || null,
    });
    ElMessage.success(`已写入（来源：${res.source || "—"}）`);
    emit("applied", res);
    close();
  } catch (e) {
    tip.value = e instanceof Error ? e.message : "刮削失败";
    ElMessage.error(tip.value);
  } finally {
    applying.value = false;
  }
}

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="刮削元数据"
    width="680px"
    class="scrape-dialog"
    :close-on-click-modal="false"
  >
    <div class="search-row">
      <div class="search-box">
        <AppIcon name="search" :size="16" />
        <input
          v-model="keyword"
          class="search-input"
          placeholder="书名 / 书号 / 详情链接"
          @keyup.enter="runSearch"
        />
      </div>
      <select v-model="source" class="source-select" aria-label="刮削源">
        <option v-for="opt in SCRAPE_SOURCE_OPTS" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <select v-model="scrapeMode" class="source-select" aria-label="刮削方式" title="API 直连 / Chrome 浏览器 / 自动">
        <option v-for="opt in SCRAPE_MODE_OPTS" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <button type="button" class="primary-btn" :disabled="loading" @click="runSearch">
        {{ loading ? "搜索中…" : "搜索" }}
      </button>
    </div>

    <p class="tip muted">{{ tip }}</p>

    <div class="local">
      <span class="tag-soft is-accent">本地</span>
      <strong>{{ localName }}</strong>
      <template v-if="localAuthor"> · {{ localAuthor }}</template>
    </div>

    <div v-loading="loading || applying" class="results">
      <div v-if="!items.length" class="empty">
        <AppIcon name="search" :size="24" />
        <span>暂无结果</span>
      </div>
      <div v-for="(hit, i) in items" :key="hit.source_id || i" class="hit-card">
        <img
          v-if="hit.cover_url"
          :src="hit.cover_url"
          alt=""
          class="hit-cover"
        />
        <div v-else class="hit-cover placeholder-cover">{{ (hit.name || "?").slice(0, 1) }}</div>
        <div class="hit-body">
          <div class="hit-title">{{ hit.name || "（无书名）" }}</div>
          <div class="hit-sub">
            <span>{{ hit.author || "佚名" }}</span>
            <span class="tag-soft">{{ hit.status || "—" }}</span>
            <span v-if="hit.category" class="tag-soft">{{ hit.category }}</span>
          </div>
          <div class="hit-meta muted-xs">
            <span v-if="hit.word_count">{{ fmtWords(hit.word_count) }}字</span>
            <span v-if="hit.latest_chapter">最新 {{ hit.latest_chapter }}</span>
            <span class="mono">ID {{ hit.source_id }} · {{ hit.source }}</span>
          </div>
        </div>
        <button type="button" class="primary-btn sm" :disabled="applying" @click="askAndApply(hit)">
          采用并写入
        </button>
      </div>
    </div>

    <template #footer>
      <button type="button" class="ghost-btn" @click="close">关闭</button>
    </template>
  </el-dialog>
</template>

<style scoped>
.search-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 180px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text-3);
}

.search-box:focus-within {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
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

.source-select {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
}

.primary-btn {
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

.primary-btn.sm {
  height: 32px;
  padding: 0 12px;
  flex-shrink: 0;
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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

.tip {
  margin: 0 0 8px;
}

.local {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  font-size: var(--text-sm);
  color: var(--color-text-2);
}

.results {
  min-height: 120px;
  max-height: 420px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px;
  color: var(--color-text-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.hit-card {
  display: flex;
  gap: 12px;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px;
  background: var(--color-surface);
  transition:
    border-color var(--duration) ease,
    box-shadow var(--duration) ease;
}

.hit-card:hover {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-sm);
}

.hit-cover {
  width: 56px;
  height: 76px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  flex-shrink: 0;
}

.placeholder-cover {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-3);
  font-weight: 600;
}

.hit-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hit-title {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.hit-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  font-size: var(--text-xs);
  color: var(--color-text-2);
}

.hit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mono {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
