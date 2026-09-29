<script setup lang="ts">
/**
 * 导入：启动/停止 + 进度条 + 实时日志 + 历史导入查询。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  IMPORT_STREAM_URL,
  cancelImport,
  fetchImportLogs,
  fetchImportStatus,
  startImport,
  type ImportLogItem,
} from "@/api/progress";
import type { ImportStatus } from "@/api/types";
import { openSse, pollStatus, type SseHandle } from "@/utils/sse";
import { useLibraryStore } from "@/stores/library";
import AppIcon from "@/components/AppIcon.vue";

const lib = useLibraryStore();

const status = ref<ImportStatus | null>(null);
const starting = ref(false);
const novelsPath = ref("NOVELS_DIR（服务端配置）");
let handle: SseHandle | null = null;

// 历史查询
const historyDate = ref<string>("");
const historyLoading = ref(false);
const historyItems = ref<ImportLogItem[]>([]);
const activeLog = ref<ImportLogItem | null>(null);

const percent = computed(() => {
  const st = status.value;
  if (!st) return 0;
  if (st.percent != null) return Math.min(100, Math.max(0, st.percent));
  const total = Number(st.total) || 0;
  const done = Number(st.done) || 0;
  return total ? Math.floor((done * 100) / total) : 0;
});

const counters = computed(() => {
  const st = status.value;
  return [
    { key: "added", label: "新增", value: st?.added_n || 0, tone: "success" },
    { key: "updated", label: "更新", value: st?.updated_n || 0, tone: "accent" },
    { key: "skipped", label: "跳过", value: st?.skipped_n || 0, tone: "muted" },
    { key: "failed", label: "失败", value: st?.failed_n || 0, tone: "danger" },
  ];
});

const progressText = computed(() => {
  const st = status.value;
  if (!st) return "";
  const total = Number(st.total) || 0;
  const done = Number(st.done) || 0;
  const head = total
    ? `导入中 ${done} / ${total}（${percent.value}%）`
    : "正在扫描 novels 目录…";
  const counts = `新增 ${st.added_n || 0} · 更新 ${st.updated_n || 0} · 跳过 ${st.skipped_n || 0} · 失败 ${st.failed_n || 0}`;
  return `${head}${st.current ? "　当前: " + st.current : ""}\n${counts}${
    st.cancel_requested ? "\n（已请求停止…）" : ""
  }`;
});

const logText = computed(() => {
  const st = status.value;
  if (!st) return "尚未运行导入。";
  const lines: string[] = [];
  if (st.running) {
    lines.push(progressText.value);
    const recent = st.recent || [];
    if (recent.length) {
      lines.push("");
      lines.push("[最近]");
      recent.forEach((x) => lines.push("  " + x));
    }
    return lines.join("\n");
  }
  const last = st.last;
  if (!last) return "尚未运行导入。";
  lines.push(last.summary || "导入已结束");
  const dump = (title: string, arr?: string[]) => {
    if (arr && arr.length) {
      lines.push(`[${title} ${arr.length}]`);
      arr.forEach((x) => lines.push("  " + (title === "失败" ? "! " : "") + x));
    }
  };
  dump("新增", last.added);
  dump("更新", last.updated);
  dump("跳过", last.skipped);
  dump("失败", last.failed);
  return lines.join("\n");
});

function stopWatch() {
  handle?.close();
  handle = null;
}

function watchProgress() {
  stopWatch();
  handle = openSse(
    IMPORT_STREAM_URL,
    (data) => {
      status.value = data as ImportStatus;
      if (!(data as ImportStatus).running) {
        stopWatch();
        ElMessage.success("导入完成");
        void Promise.all([lib.loadBooks(), lib.loadStats(), loadHistory()]);
      }
    },
    {
      shouldStop: (d) => !(d as ImportStatus).running,
      onFallback: () => {
        handle = pollStatus(
          fetchImportStatus,
          (data) => {
            status.value = data as ImportStatus;
            if (!(data as ImportStatus).running) {
              stopWatch();
              ElMessage.success("导入完成");
              void Promise.all([lib.loadBooks(), lib.loadStats(), loadHistory()]);
            }
          },
          { shouldStop: (d) => !(d as ImportStatus).running },
        );
      },
    },
  );
}

async function onStart() {
  starting.value = true;
  try {
    const res = await startImport();
    ElMessage.success(res.started ? "导入已开始" : "导入已在进行中");
    status.value = res.import;
    watchProgress();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "导入失败");
  } finally {
    starting.value = false;
  }
}

async function onCancel() {
  try {
    const res = await cancelImport();
    ElMessage[res.ok ? "success" : "warning"](res.ok ? "已请求停止导入" : "当前没有进行中的导入");
    status.value = res.import;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "停止失败");
  }
}

async function onRefresh() {
  try {
    status.value = await fetchImportStatus();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "刷新失败");
  }
}

async function loadHistory() {
  historyLoading.value = true;
  try {
    const res = await fetchImportLogs(historyDate.value || undefined);
    historyItems.value = res.items || [];
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载历史失败");
  } finally {
    historyLoading.value = false;
  }
}

function showLogDetail(row: ImportLogItem) {
  activeLog.value = row;
}

onMounted(async () => {
  await onRefresh();
  if (status.value?.running) watchProgress();
  try {
    await lib.loadStats();
    if (lib.stats?.novels_dir) novelsPath.value = lib.stats.novels_dir;
  } catch {
    /* ignore */
  }
  await loadHistory();
});

onUnmounted(stopWatch);
</script>

<template>
  <div class="page import-page">
    <header class="page-header">
      <h1 class="page-title">导入</h1>
      <div class="page-actions">
        <button type="button" class="primary-btn" :disabled="starting" @click="onStart">
          <AppIcon name="play" :size="14" />
          {{ starting ? "启动中…" : "开始导入" }}
        </button>
        <button type="button" class="ghost-btn danger" @click="onCancel">
          <AppIcon name="stop" :size="14" />
          停止
        </button>
        <button type="button" class="ghost-btn" @click="onRefresh">
          <AppIcon name="refresh" :size="14" />
          刷新
        </button>
        <el-tooltip placement="bottom" effect="dark">
          <template #content>
            <div class="tip-body">
              导入来源 · 本地：扫描服务端 NOVELS_DIR（如 novels/起点/都市/书名.txt）。<br />
              章节解析进 SQLite，阅读不依赖网盘。内容哈希未变则跳过。<br />
              <span class="mono">{{ novelsPath }}</span>
            </div>
          </template>
          <span class="help-icon">?</span>
        </el-tooltip>
      </div>
    </header>

    <section class="page-card">
      <div class="section-head">
        <h2 class="section-title">导入进度</h2>
        <span v-if="status?.running" class="tag-soft is-accent">进行中</span>
        <span v-else-if="status?.last" class="tag-soft">已结束</span>
      </div>

      <template v-if="status?.running || status?.last">
        <div class="progress-row">
          <el-progress
            :percentage="percent"
            :stroke-width="10"
            :status="status?.cancel_requested ? 'warning' : undefined"
          />
        </div>
        <div class="counters">
          <div v-for="c in counters" :key="c.key" class="counter" :class="`tone-${c.tone}`">
            <div class="num">{{ c.value }}</div>
            <div class="lab">{{ c.label }}</div>
          </div>
        </div>
        <p v-if="status?.current" class="current muted">
          当前：{{ status.current }}
        </p>
      </template>
      <p v-else class="muted">当前没有进行中的导入。</p>

      <h2 class="section-title">导入日志</h2>
      <pre class="log-panel">{{ logText }}</pre>
    </section>

    <section class="page-card">
      <h2 class="section-title">历史导入</h2>
      <div class="history-bar">
        <el-date-picker
          v-model="historyDate"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期（可选）"
          clearable
          @change="loadHistory"
        />
        <button type="button" class="ghost-btn" :disabled="historyLoading" @click="loadHistory">
          查询
        </button>
      </div>
      <el-table
        v-loading="historyLoading"
        :data="historyItems"
        size="small"
        class="history-table"
        @row-click="showLogDetail"
      >
        <el-table-column prop="finished_at" label="完成时间" width="170" />
        <el-table-column prop="summary" label="摘要" min-width="200" />
        <el-table-column prop="added_n" label="新增" width="70" />
        <el-table-column prop="updated_n" label="更新" width="70" />
        <el-table-column prop="skipped_n" label="跳过" width="70" />
        <el-table-column prop="failed_n" label="失败" width="70" />
      </el-table>

      <template v-if="activeLog">
        <h2 class="section-title">
          记录详情 #{{ activeLog.id }}（{{ activeLog.finished_at }}）
        </h2>
        <pre class="log-panel">{{ activeLog.summary }}
{{ (activeLog.added_list || activeLog.detail?.added || []).join("\n") }}</pre>
      </template>
    </section>
  </div>
</template>

<style scoped>
.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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

.primary-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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

.ghost-btn:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.ghost-btn.danger {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.ghost-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--space-2);
}

.section-head .section-title {
  margin: 0;
}

.progress-row {
  margin: var(--space-2) 0 var(--space-3);
}

.counters {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: var(--space-3);
}

.counter {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  text-align: center;
}

.counter .num {
  font-size: var(--text-xl);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.counter .lab {
  font-size: var(--text-xs);
  color: var(--color-text-3);
  margin-top: 2px;
}

.counter.tone-success .num {
  color: var(--color-success);
}

.counter.tone-accent .num {
  color: var(--color-accent);
}

.counter.tone-danger .num {
  color: var(--color-danger);
}

.current {
  margin: 0 0 var(--space-3);
}

.section-title {
  margin: var(--space-4) 0 var(--space-2);
}

.section-title:first-child {
  margin-top: 0;
}

.help-icon {
  cursor: default;
  color: var(--color-text-3);
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  line-height: 1;
  user-select: none;
}

.tip-body {
  max-width: 360px;
  line-height: 1.7;
}

.history-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.history-table {
  cursor: pointer;
  margin-bottom: 12px;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 576px) {
  .counters {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
