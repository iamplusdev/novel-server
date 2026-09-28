<script setup lang="ts">
/**
 * 书库体检 + 一键刮削（批量）。P7 补全体检报告操作。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  BATCH_STREAM_URL,
  cancelBatchScrape,
  fetchBatchStatus,
  startBatchScrape,
} from "@/api/progress";
import type { BatchStatus } from "@/api/types";
import { openSse, pollStatus, type SseHandle } from "@/utils/sse";
import { useLibraryStore } from "@/stores/library";

const lib = useLibraryStore();

const batch = ref<BatchStatus | null>(null);
const source = ref("qidian");
const onlyMissing = ref(true);
const minScore = ref(0.55);
const dryRun = ref(false);
const starting = ref(false);
let handle: SseHandle | null = null;

const batchLog = computed(() => {
  const st = batch.value;
  if (!st) return "尚未运行。";
  const lines: string[] = [];
  if (st.running) {
    lines.push(
      `刮削中 ${st.done || 0} / ${st.total || "?"} · 匹配 ${st.matched || 0} · 跳过 ${
        st.skipped || 0
      } · 失败 ${st.failed || 0}${st.cancel_requested ? "（已请求停止…）" : ""}`,
    );
  } else {
    lines.push(
      `已完成 ${st.done || 0} / ${st.total || 0} · 匹配 ${st.matched || 0} · 跳过 ${
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
        void Promise.all([lib.loadBooks(), lib.loadStats()]);
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
              void Promise.all([lib.loadBooks(), lib.loadStats()]);
            }
          },
          { shouldStop: (d) => !(d as BatchStatus).running },
        );
      },
    },
  );
}

async function onStart() {
  starting.value = true;
  try {
    const res = await startBatchScrape({
      source: source.value,
      only_missing: onlyMissing.value,
      min_score: minScore.value,
      dry_run: dryRun.value,
    });
    batch.value = res.status;
    ElMessage.success(res.started ? "批量刮削已开始" : "已有任务在运行");
    watchBatch();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "启动失败");
  } finally {
    starting.value = false;
  }
}

async function onCancel() {
  try {
    const res = await cancelBatchScrape();
    batch.value = res.status;
    ElMessage[res.ok ? "success" : "warning"](res.ok ? "已请求停止" : "当前没有进行中的任务");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "停止失败");
  }
}

async function onRefresh() {
  try {
    batch.value = await fetchBatchStatus();
    if (batch.value?.running) watchBatch();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "刷新失败");
  }
}

onMounted(onRefresh);
onUnmounted(stopWatch);
</script>

<template>
  <div class="check-page">
    <header class="toolbar">
      <h2>书库体检</h2>
      <el-tag type="info" round>体检报告将在阶段 7 接入</el-tag>
    </header>

    <div class="page-card">
      <h3>一键刮削（全库）</h3>
      <p class="muted">
        按所选刮削源对书库批量识别：以<strong>书名+作者</strong>相似度取最近匹配，再拉详情写入（含封面/标签/来源）。
        默认只处理尚未刮削的书；建议先「预览匹配」再「开始写入」。每本间隔约 0.6s，降低风控。
      </p>
      <div class="controls">
        <span class="label">刮削源</span>
        <el-select v-model="source" style="width: 110px">
          <el-option label="起点" value="qidian" />
          <el-option label="番茄" value="fanqie" />
          <el-option label="纵横" value="zongheng" />
        </el-select>
        <el-checkbox v-model="onlyMissing">仅未刮削</el-checkbox>
        <el-checkbox v-model="dryRun">预览匹配（不写入）</el-checkbox>
        <span class="label">匹配阈值</span>
        <el-input-number
          v-model="minScore"
          :min="0.3"
          :max="1"
          :step="0.05"
          controls-position="right"
          style="width: 100px"
        />
        <el-button type="primary" :loading="starting" @click="onStart">
          {{ dryRun ? "预览匹配" : "开始一键刮削" }}
        </el-button>
        <el-button type="danger" plain @click="onCancel">停止</el-button>
        <el-button @click="onRefresh">刷新进度</el-button>
      </div>
      <pre class="log">{{ batchLog }}</pre>
    </div>
  </div>
</template>

<style scoped>
.check-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
}

h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.log {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
