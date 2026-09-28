<script setup lang="ts">
/**
 * 导入本地 novels 目录 TXT：启动/停止 + SSE 进度 + 日志。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  IMPORT_STREAM_URL,
  cancelImport,
  fetchImportStatus,
  startImport,
} from "@/api/progress";
import type { ImportStatus } from "@/api/types";
import { openSse, pollStatus, type SseHandle } from "@/utils/sse";
import { useLibraryStore } from "@/stores/library";

// 仅用 library store 的刷新；避免重复实现
const lib = useLibraryStore();

const status = ref<ImportStatus | null>(null);
const starting = ref(false);
const novelsPath = ref("NOVELS_DIR（服务端配置）");
let handle: SseHandle | null = null;

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
        void Promise.all([lib.loadBooks(), lib.loadStats()]);
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
              void Promise.all([lib.loadBooks(), lib.loadStats()]);
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
    ElMessage.success(res.started ? "本地导入已开始" : "导入已在进行中");
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

onMounted(async () => {
  await onRefresh();
  if (status.value?.running) watchProgress();
  // 读取 stats 里的 novels_dir
  try {
    await lib.loadStats();
    if (lib.stats?.novels_dir) novelsPath.value = lib.stats.novels_dir;
  } catch {
    /* ignore */
  }
});

onUnmounted(stopWatch);
</script>

<template>
  <div class="import-page">
    <header class="toolbar">
      <h2>导入 TXT</h2>
      <div class="actions">
        <el-button type="primary" :loading="starting" @click="onStart">导入本地 novels</el-button>
        <el-button type="danger" plain @click="onCancel">停止</el-button>
        <el-button @click="onRefresh">刷新状态</el-button>
      </div>
    </header>

    <div class="page-card">
      <h3>导入来源</h3>
      <p class="muted">
        <strong>本地</strong>：扫描服务端 NOVELS_DIR（如 <code>novels/玄幻/书名.txt</code>）。<br />
        章节解析进 SQLite，阅读不依赖网盘。内容哈希未变则跳过。
      </p>
      <p class="mono muted">{{ novelsPath }}</p>
    </div>

    <div class="page-card">
      <h3>导入进度</h3>
      <template v-if="status?.running">
        <el-progress :percentage="percent" :stroke-width="10" />
        <pre class="log">{{ progressText }}</pre>
      </template>
      <p v-else class="muted">当前没有进行中的导入。</p>

      <h3>导入日志</h3>
      <pre class="log">{{ logText }}</pre>
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

code {
  font-family: ui-monospace, Consolas, monospace;
  background: var(--el-fill-color-light);
  padding: 1px 4px;
  border-radius: 4px;
}
</style>
