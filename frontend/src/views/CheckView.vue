<script setup lang="ts">
/**
 * 书库体检：重复 / 异常 / 刮削 三页签。
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  BATCH_STREAM_URL,
  cancelBatchScrape,
  fetchBatchStatus,
  startBatchScrape,
} from "@/api/progress";
import {
  fetchLibraryReport,
  mergeDuplicates,
  relocateBooks,
  repairAll,
  repairOne,
} from "@/api/library";
import type { BatchStatus, LibraryReport } from "@/api/types";
import { openSse, pollStatus, type SseHandle } from "@/utils/sse";
import { useLibraryStore } from "@/stores/library";
import AppIcon from "@/components/AppIcon.vue";

const router = useRouter();
const route = useRoute();
const lib = useLibraryStore();

const activeTab = ref("dup");
// 支持 ?tab=dup|issue|scrape（书库「批量刮削」跳转用）
watch(
  () => route.query.tab,
  (t) => {
    if (t === "dup" || t === "issue" || t === "scrape") activeTab.value = t;
  },
  { immediate: true },
);
const report = ref<LibraryReport | null>(null);
const reportLoading = ref(false);

const batch = ref<BatchStatus | null>(null);
/** all=按起点→番茄→纵横顺序，命中即停 */
const source = ref("all");
const onlyMissing = ref(true);
const minScore = ref(0.8);
const starting = ref(false);
const acting = ref(false);
let handle: SseHandle | null = null;

const summary = computed(() => {
  const r = report.value;
  if (!r) return "未检查";
  return `重复 ${r.duplicate_groups || 0} 组 · 异常 ${r.issue_count || 0}`;
});

const batchPercent = computed(() => {
  const st = batch.value;
  if (!st) return 0;
  const total = Number(st.total) || 0;
  const done = Number(st.done) || 0;
  return total ? Math.min(100, Math.floor((done * 100) / total)) : 0;
});

const batchLog = computed(() => {
  const st = batch.value;
  if (!st) return "尚未运行。";
  const lines: string[] = [];
  if (st.running) {
    lines.push(
      `刮削中 ${st.done || 0} / ${st.total || "?"} · 写入 ${st.matched || 0} · 跳过 ${
        st.skipped || 0
      } · 失败 ${st.failed || 0}${st.cancel_requested ? "（已请求停止…）" : ""}`,
    );
  } else {
    lines.push(
      `已完成 ${st.done || 0} / ${st.total || 0} · 写入 ${st.matched || 0} · 跳过 ${
        st.skipped || 0
      } · 失败 ${st.failed || 0}`,
    );
    if (st.last_error) lines.push("最近错误: " + st.last_error);
  }
  const log = st.log || [];
  if (log.length) {
    lines.push("");
    log.forEach((x) => lines.push(`${x.time}  ${x.message}`));
  }
  return lines.join("\n");
});

const kindLabel: Record<string, string> = {
  chapter_parse: "未分章",
  encoding: "乱码",
  control_chars: "控制符",
  empty_chapters: "空章节",
  source_missing: "缺源文件",
};

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
}

async function loadReport() {
  reportLoading.value = true;
  try {
    report.value = await fetchLibraryReport();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载体检报告失败");
  } finally {
    reportLoading.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadReport(), lib.loadBooks(), lib.loadStats()]);
}

async function onMerge(g: NonNullable<LibraryReport["duplicates"]>[number]) {
  const del = (g.books || []).filter((b) => b.id !== g.keep_id).map((b) => b.id);
  try {
    await ElMessageBox.confirm(
      `合并《${g.title}》\n保留 ID ${g.keep_id}，删除 ${del.join(", ")}？`,
      "合并重复书",
      { type: "warning", confirmButtonText: "合并", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  acting.value = true;
  try {
    const res = await mergeDuplicates(g.keep_id, del);
    ElMessage.success(`已合并，删除 ${(res.deleted || []).length} 本`);
    await refreshAll();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "合并失败");
  } finally {
    acting.value = false;
  }
}

async function onRepairOne(bookId: number) {
  acting.value = true;
  try {
    const res = await repairOne(bookId, "auto");
    ElMessage.success(`${res.title || ""}：${(res.actions || []).join("；") || "已处理"}`);
    await refreshAll();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "修复失败");
  } finally {
    acting.value = false;
  }
}

async function onRepairAll() {
  try {
    await ElMessageBox.confirm(
      "对所有异常书执行自动修复？\n（清理字符，必要时从源 TXT 重解析）",
      "修复全部",
      { type: "warning", confirmButtonText: "修复", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  acting.value = true;
  try {
    const res = await repairAll("auto");
    ElMessage.success(`已修复 ${res.count || 0} 本`);
    await refreshAll();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "修复失败");
  } finally {
    acting.value = false;
  }
}

async function onRelocate() {
  try {
    await ElMessageBox.confirm(
      "按书籍分类归位源 TXT？\n将把「未分类」等目录中的文件移到对应分类文件夹（只移动位置，不改内容）。",
      "按分类归位",
      { type: "warning", confirmButtonText: "归位", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  acting.value = true;
  try {
    const res = await relocateBooks();
    ElMessage.success(`归位完成：移动 ${res.moved || 0} 本 · 失败 ${res.failed || 0} 本`);
    await refreshAll();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "归位失败");
  } finally {
    acting.value = false;
  }
}

function stopWatch() {
  handle?.close();
  handle = null;
}

function watchBatch() {
  stopWatch();
  handle = openSse(
    BATCH_STREAM_URL,
    (data) => {
      batch.value = data as BatchStatus;
      if (!(data as BatchStatus).running) {
        stopWatch();
        ElMessage.success("批量刮削完成");
        void refreshAll();
      }
    },
    {
      shouldStop: (d) => !(d as BatchStatus).running,
      onFallback: () => {
        handle = pollStatus(
          fetchBatchStatus,
          (data) => {
            batch.value = data as BatchStatus;
            if (!(data as BatchStatus).running) {
              stopWatch();
              ElMessage.success("批量刮削完成");
              void refreshAll();
            }
          },
          { shouldStop: (d) => !(d as BatchStatus).running },
        );
      },
    },
  );
}

async function onStartBatch() {
  starting.value = true;
  try {
    const res = await startBatchScrape({
      source: source.value,
      only_missing: onlyMissing.value,
      min_score: minScore.value,
    });
    batch.value = res.status;
    ElMessage.success(res.started ? "一键刮削已开始" : "批处理已在运行");
    watchBatch();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "启动失败");
  } finally {
    starting.value = false;
  }
}

async function onCancelBatch() {
  try {
    const res = await cancelBatchScrape();
    batch.value = res.status;
    ElMessage[res.ok ? "success" : "warning"](res.ok ? "已请求停止" : "当前没有进行中的任务");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "停止失败");
  }
}

async function onRefreshBatch() {
  try {
    batch.value = await fetchBatchStatus();
    if (batch.value?.running) watchBatch();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "刷新失败");
  }
}

onMounted(async () => {
  await Promise.all([loadReport(), onRefreshBatch()]);
});
onUnmounted(stopWatch);
</script>

<template>
  <div v-loading="reportLoading || acting" class="page check-page">
    <header class="page-header">
      <div class="title-row">
        <h1 class="page-title">书库体检</h1>
        <span class="count-pill">{{ summary }}</span>
      </div>
      <div class="page-actions">
        <button type="button" class="ghost-btn" @click="loadReport">
          <AppIcon name="refresh" :size="14" />
          重新扫描
        </button>
        <button type="button" class="ghost-btn" @click="onRepairAll">修复全部问题</button>
        <button
          type="button"
          class="ghost-btn"
          title="按书籍分类把本地 TXT 移到对应分类文件夹"
          @click="onRelocate"
        >
          按分类归位
        </button>
      </div>
    </header>

    <section class="page-card tabs-card">
      <div class="tab-nav" role="tablist">
        <button
          type="button"
          class="tab-btn"
          :class="{ 'is-active': activeTab === 'dup' }"
          @click="activeTab = 'dup'"
        >
          重复书籍
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ 'is-active': activeTab === 'issue' }"
          @click="activeTab = 'issue'"
        >
          异常书籍
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ 'is-active': activeTab === 'scrape' }"
          @click="activeTab = 'scrape'"
        >
          刮削书籍
        </button>
      </div>

      <!-- 重复书籍 -->
      <div v-if="activeTab === 'dup'" class="tab-panel">
        <p class="muted">
          合并规则：保留章节/字数最多的一本，删除其余重复项（章节与多余封面一并删，源 TXT 不动）。
        </p>
        <div v-if="!report?.duplicates?.length" class="empty">
          <AppIcon name="check" :size="24" />
          <span>没有发现重复书。</span>
        </div>
        <div v-for="(g, gi) in report?.duplicates || []" :key="gi" class="check-item">
          <div class="body">
            <div class="title">
              {{ g.title }}<template v-if="g.author"> · {{ g.author }}</template>
            </div>
            <div v-for="b in g.books" :key="b.id" class="muted row">
              <span class="tag-soft" :class="b.id === g.keep_id ? 'is-success' : ''">
                {{ b.id === g.keep_id ? "保留" : "待删" }}
              </span>
              <span>
                ID {{ b.id }} · {{ b.chapter_count ?? 0 }} 章 · {{ fmtWords(b.word_count) }}
                · <span class="mono">{{ b.source_path || "" }}</span>
              </span>
            </div>
          </div>
          <button type="button" class="primary-btn sm" @click="onMerge(g)">一键合并</button>
        </div>
      </div>

      <!-- 异常书籍 -->
      <div v-else-if="activeTab === 'issue'" class="tab-panel">
        <p class="muted">修复：清理控制字符；若源 TXT 仍可读且未分章/乱码，则重新解析章节。</p>
        <div v-if="!report?.issues?.length" class="empty">
          <AppIcon name="check" :size="24" />
          <span>没有发现异常，书库健康。</span>
        </div>
        <div v-for="it in report?.issues || []" :key="it.book_id + it.kind" class="check-item">
          <div class="body">
            <div class="title">
              {{ it.title }}
              <span class="tag-soft is-warning">{{ kindLabel[it.kind] || it.kind }}</span>
            </div>
            <div class="muted">{{ it.message }} · ID {{ it.book_id }}</div>
          </div>
          <div class="ops">
            <button type="button" class="ghost-btn sm" @click="onRepairOne(it.book_id)">修复</button>
            <button
              type="button"
              class="link-btn"
              @click="router.push({ name: 'book-detail', params: { id: String(it.book_id) } })"
            >
              编辑
            </button>
          </div>
        </div>
      </div>

      <!-- 刮削书籍 -->
      <div v-else class="tab-panel">
        <p class="muted">
          按所选刮削源对书库批量识别：以<strong>书名+作者</strong>相似度取最近匹配后写入。
          选「全部」时按<strong>起点 → 番茄 → 纵横</strong>顺序，达到阈值即写入并停止，不再试后续书源。
        </p>
        <div class="controls">
          <span class="label">刮削源</span>
          <select v-model="source" class="field-input">
            <option value="all">全部（顺序匹配）</option>
            <option value="qidian">起点</option>
            <option value="fanqie">番茄</option>
            <option value="zongheng">纵横</option>
          </select>
          <label class="check-label">
            <input v-model="onlyMissing" type="checkbox" />
            仅未刮削
          </label>
          <span class="label">匹配阈值</span>
          <input
            v-model.number="minScore"
            type="number"
            min="0.3"
            max="1"
            step="0.05"
            class="field-input narrow"
          />
          <button type="button" class="primary-btn" :disabled="starting" @click="onStartBatch">
            {{ starting ? "启动中…" : "开始一键刮削" }}
          </button>
          <button type="button" class="ghost-btn danger" @click="onCancelBatch">停止</button>
          <button type="button" class="ghost-btn" @click="onRefreshBatch">刷新进度</button>
        </div>

        <div v-if="batch" class="batch-status">
          <div class="status-line">
            <span
              class="status-dot"
              :class="batch.running ? 'is-info' : batch.failed ? 'is-danger' : 'is-success'"
            >
              {{ batch.running ? "运行中" : "已结束" }}
            </span>
            <span class="muted">
              {{ batch.done || 0 }} / {{ batch.total || 0 }} · 写入 {{ batch.matched || 0 }}
              · 跳过 {{ batch.skipped || 0 }} · 失败 {{ batch.failed || 0 }}
            </span>
            <span class="progress-label">{{ batchPercent }}%</span>
          </div>
          <div class="progress-track">
            <div
              class="progress-bar"
              :class="{ 'is-success': !batch.running && batchPercent >= 100 }"
              :style="{ width: batchPercent + '%' }"
            />
          </div>
        </div>

        <pre class="log-panel">{{ batchLog }}</pre>
      </div>
    </section>
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

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.ghost-btn.sm {
  height: 32px;
  padding: 0 12px;
}

.ghost-btn:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.ghost-btn.danger {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.primary-btn {
  display: inline-flex;
  align-items: center;
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
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tabs-card {
  padding: var(--space-3) var(--space-4) var(--space-4);
}

.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--space-4);
}

.tab-btn {
  border: none;
  background: none;
  padding: 10px 14px;
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: inherit;
  color: var(--color-text-2);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--color-text);
}

.tab-btn.is-active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
  font-weight: 600;
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px;
  color: var(--color-text-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.check-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.body {
  flex: 1;
  min-width: 0;
}

.title {
  font-weight: 600;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.ops {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.label {
  font-size: var(--text-xs);
  color: var(--color-text-3);
}

.field-input {
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
}

.field-input.narrow {
  width: 88px;
}

.check-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  color: var(--color-text-2);
  cursor: pointer;
}

.check-label input {
  accent-color: var(--color-accent);
}

.link-btn {
  border: none;
  background: none;
  color: var(--color-accent);
  font-size: var(--text-sm);
  cursor: pointer;
  font-family: inherit;
  padding: 0 4px;
}

.batch-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.progress-track {
  height: 6px;
  border-radius: var(--radius-full);
  background: var(--color-surface-3);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--color-accent);
  border-radius: inherit;
  transition: width 0.25s ease;
}

.mono {
  font-family: var(--font-mono);
  font-size: 11px;
  word-break: break-all;
}
</style>
