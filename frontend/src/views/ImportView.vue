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
  <div class="import-page">
    <header class="toolbar">
      <h2>导入</h2>
      <div class="actions">
        <el-button type="primary" :loading="starting" @click="onStart">导入</el-button>
        <el-button type="danger" plain @click="onCancel">停止</el-button>
        <el-button @click="onRefresh">刷新状态</el-button>
        <!-- 导入来源说明：不占页面区块，仅 ? 悬浮 -->
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

    <div class="page-card">
      <h3>导入进度</h3>
      <template v-if="status?.running">
        <el-progress
          :percentage="percent"
          :stroke-width="12"
          :status="status.cancel_requested ? 'warning' : undefined"
        />
        <pre class="log">{{ progressText }}</pre>
      </template>
      <p v-else class="muted">当前没有进行中的导入。</p>

      <h3>导入日志</h3>
      <pre class="log">{{ logText }}</pre>
    </div>

    <div class="page-card">
      <h3>历史导入</h3>
      <div class="history-bar">
        <el-date-picker
          v-model="historyDate"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期（可选）"
          clearable
          @change="loadHistory"
        />
        <el-button :loading="historyLoading" @click="loadHistory">查询</el-button>
      </div>
      <el-table
        v-loading="historyLoading"
        :data="historyItems"
        size="small"
        @row-click="showLogDetail"
        class="history-table"
      >
        <el-table-column prop="finished_at" label="完成时间" width="170" />
        <el-table-column prop="summary" label="摘要" min-width="200" />
        <el-table-column prop="added_n" label="新增" width="70" />
        <el-table-column prop="updated_n" label="更新" width="70" />
        <el-table-column prop="skipped_n" label="跳过" width="70" />
        <el-table-column prop="failed_n" label="失败" width="70" />
      </el-table>

      <template v-if="activeLog">
        <h3>记录详情 #{{ activeLog.id }}（{{ activeLog.finished_at }}）</h3>
        <pre class="log">{{ activeLog.summary }}
{{ (activeLog.added_list || activeLog.detail?.added || []).join("\n") }}</pre>
      </template>
    </div>
  </div>
</template>

<style scoped>
.import-page {
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

.toolbar h2 {
  margin: 0;
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.row-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}

.help-icon {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid var(--el-border-color);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  line-height: 1;
  user-select: none;
}

.help-icon:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
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

.log {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 8px 0 0;
}

.muted {
  color: var(--el-text-color-secondary);
}

.mono {
  font-family: ui-monospace, Consolas, monospace;
}
</style>
