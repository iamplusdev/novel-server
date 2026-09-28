<script setup lang="ts">
/**
 * 书库体检：重复合并、异常修复、归位 + 一键刮削。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
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

const router = useRouter();
const lib = useLibraryStore();

const report = ref<LibraryReport | null>(null);
const reportLoading = ref(false);
const batch = ref<BatchStatus | null>(null);
const source = ref("qidian");
const onlyMissing = ref(true);
const minScore = ref(0.55);
const dryRun = ref(false);
const starting = ref(false);
const acting = ref(false);
let handle: SseHandle | null = null;

const summary = computed(() => {
  const r = report.value;
  if (!r) return "未检查";
  return `重复 ${r.duplicate_groups || 0} 组 · 异常 ${r.issue_count || 0}`;
});

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
      `已完成 ${st.done || 0} / ${st.total || 0}${st.dry_run ? "（预览）" : ""} · 匹配 ${
        st.matched || 0
      } · 跳过 ${st.skipped || 0} · 失败 ${st.failed || 0}`,
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
      dry_run: dryRun.value,
    });
    batch.value = res.status;
    ElMessage.success(res.started ? (dryRun.value ? "预览匹配已开始" : "一键刮削已开始") : "批处理已在运行");
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
  <div class="check-page" v-loading="reportLoading || acting">
    <header class="toolbar">
      <div class="toolbar-left">
        <h2>书库体检</h2>
        <el-tag round type="info">{{ summary }}</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button @click="loadReport">重新扫描</el-button>
        <el-button @click="onRepairAll">修复全部问题</el-button>
        <el-button
          title="按书籍分类把本地 TXT 移到对应分类文件夹"
          @click="onRelocate"
        >
          按分类归位
        </el-button>
      </div>
    </header>

    <div class="page-card">
      <h3>重复书籍（同书名+作者）</h3>
      <p class="muted">
        合并规则：保留章节/字数最多的一本，删除其余重复项（章节与多余封面一并删，源 TXT 不动）。
      </p>
      <el-empty
        v-if="!report?.duplicates?.length"
        description="没有发现重复书。"
        :image-size="60"
      />
      <div v-for="(g, gi) in report?.duplicates || []" :key="gi" class="check-item">
        <div class="body">
          <div class="title">
            {{ g.title }}<template v-if="g.author"> · {{ g.author }}</template>
          </div>
          <div
            v-for="b in g.books"
            :key="b.id"
            class="muted row"
          >
            <el-tag size="small" :type="b.id === g.keep_id ? 'success' : 'info'">
              {{ b.id === g.keep_id ? "保留" : "待删" }}
            </el-tag>
            <span>
              ID {{ b.id }} · {{ b.chapter_count ?? 0 }} 章 · {{ fmtWords(b.word_count) }}
              · <span class="mono">{{ b.source_path || "" }}</span>
            </span>
          </div>
        </div>
        <el-button type="primary" size="small" @click="onMerge(g)">一键合并</el-button>
      </div>
    </div>

    <div class="page-card">
      <h3>异常书籍</h3>
      <p class="muted">
        修复：清理控制字符；若源 TXT 仍可读且未分章/乱码，则重新解析章节。
      </p>
      <el-empty
        v-if="!report?.issues?.length"
        description="没有发现异常，书库健康。"
        :image-size="60"
      />
      <div v-for="it in report?.issues || []" :key="it.book_id + it.kind" class="check-item">
        <div class="body">
          <div class="title">
            {{ it.title }}
            <el-tag size="small">{{ kindLabel[it.kind] || it.kind }}</el-tag>
          </div>
          <div class="muted">{{ it.message }} · ID {{ it.book_id }}</div>
        </div>
        <div class="ops">
          <el-button size="small" @click="onRepairOne(it.book_id)">修复</el-button>
          <el-button
            size="small"
            text
            type="primary"
            @click="router.push({ name: 'book-detail', params: { id: String(it.book_id) } })"
          >
            编辑
          </el-button>
        </div>
      </div>
    </div>

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
        <el-button type="primary" :loading="starting" @click="onStartBatch">
          {{ dryRun ? "预览匹配" : "开始一键刮削" }}
        </el-button>
        <el-button type="danger" plain @click="onCancelBatch">停止</el-button>
        <el-button @click="onRefreshBatch">刷新进度</el-button>
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
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-left h2 {
  margin: 0;
}

.toolbar-right {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.check-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--app-border);
}

.check-item:last-child {
  border-bottom: none;
}

.body {
  flex: 1;
  min-width: 0;
}

.title {
  font-weight: 600;
  margin-bottom: 4px;
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

.mono {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  word-break: break-all;
}
</style>
