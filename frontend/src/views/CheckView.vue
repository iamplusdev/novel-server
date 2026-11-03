<script setup lang="ts">
/**
 * 书库体检：重复 / 异常 / 刮削 三页签。
 * 进入页面不自动扫描；点「开始/重新扫描」才执行（快速/深度可选），结果缓存在会话内。
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  BATCH_STREAM_URL,
  cancelBatchScrape,
  fetchBatchStatus,
  fetchTasksStatus,
  startBatchScrape,
} from "@/api/progress";
import {
  SCAN_STREAM_URL,
  cancelScan,
  fetchScanStatus,
  mergeDuplicates,
  previewRepair,
  relocateBooks,
  repairAll,
  startScan,
} from "@/api/library";
import type {
  BatchStatus,
  LibraryReport,
  RepairPreviewItem,
  ScanStatus,
  TasksStatus,
} from "@/api/types";
import { rebuildThumbs } from "@/api/admin";
import { SCRAPE_MODE_OPTS } from "@/api/scrape";
import { openSse, pollStatus, type SseHandle } from "@/utils/sse";
import { useLibraryStore } from "@/stores/library";
import { useCheckStore } from "@/stores/check";
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
// 报告缓存在 Pinia（内存态，避免 sessionStorage 5MB 上限导致大报告静默丢失）
const check = useCheckStore();
const report = computed(() => check.report);
const scanned = computed(() => check.scanned);
/** 深度体检：读正文查乱码/控制符，大库较慢（改为后台任务，带进度） */
const deepScan = ref(false);
/** 后台体检任务状态 */
const scan = ref<ScanStatus | null>(null);
let scanHandle: SseHandle | null = null;

// 互斥任务：导入/体检/刮削同一时刻只允许一个在跑
const tasks = ref<TasksStatus | null>(null);
let tasksTimer: ReturnType<typeof setInterval> | null = null;
const scanBlocked = computed(() => {
  const t = tasks.value;
  if (!t) return "";
  if (t.import) return "导入";
  if (t.scrape) return "刮削";
  return "";
});
const scrapeBlocked = computed(() => {
  const t = tasks.value;
  if (!t) return "";
  if (t.import) return "导入";
  if (t.scan) return "体检";
  return "";
});

async function refreshTasks() {
  try {
    tasks.value = await fetchTasksStatus();
  } catch {
    /* ignore */
  }
}

const scanPercent = computed(() => {
  const st = scan.value;
  if (!st) return 0;
  return Math.min(100, Math.max(0, Number(st.percent) || 0));
});

const batch = ref<BatchStatus | null>(null);
/** all=按起点→番茄→纵横顺序，命中即停 */
const source = ref("all");
const onlyMissing = ref(true);
const minScore = ref(0.7);
/** 刮削取数方式：api（默认）/ auto（API 优先）/ chrome（备用） */
const scrapeMode = ref("api");
const starting = ref(false);
const acting = ref(false);
const repairPreviewOpen = ref(false);
const repairPreviewLoading = ref(false);
const repairPreviewTitle = ref("修复预览");
const repairPreviewItems = ref<RepairPreviewItem[]>([]);
const repairPreviewActionable = computed(() =>
  repairPreviewItems.value.some((it) => !it.error),
);
let repairPreviewIds: number[] = [];
let repairPreviewMode = "auto";
let repairPreviewSeq = 0;
let handle: SseHandle | null = null;

const summary = computed(() => {
  if (!scanned.value) return "未扫描";
  const r = report.value;
  if (!r) return "未检查";
  return `重复 ${r.duplicate_groups || 0} 组 · 异常 ${r.issue_count || 0}${r.deep ? " · 深度" : ""}`;
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

/** 批量刮削结构化结果：状态筛选 + CSV 导出 */
const batchActionFilter = ref("all");
const batchActionLabel: Record<string, string> = {
  matched: "写入",
  recovered: "兜底恢复",
  skipped: "跳过",
  failed: "失败",
};
const batchResults = computed(() => batch.value?.results || []);
const batchActionOptions = computed(() => {
  const counts = new Map<string, number>();
  for (const r of batchResults.value) {
    counts.set(r.action, (counts.get(r.action) || 0) + 1);
  }
  const known = Object.keys(batchActionLabel);
  const extras = [...counts.keys()].filter((k) => !known.includes(k)).sort();
  return [
    { action: "all", label: "全部", count: batchResults.value.length },
    ...known.map((action) => ({
      action,
      label: batchActionLabel[action],
      count: counts.get(action) || 0,
    })),
    ...extras.map((action) => ({
      action,
      label: action,
      count: counts.get(action) || 0,
    })),
  ];
});
const filteredBatchResults = computed(() =>
  batchActionFilter.value === "all"
    ? batchResults.value
    : batchResults.value.filter((r) => r.action === batchActionFilter.value),
);

function batchActionClass(action: string): string {
  if (action === "matched" || action === "recovered") return "is-success";
  if (action === "skipped") return "is-warning";
  return "is-danger";
}

function exportBatchReport() {
  const rows = filteredBatchResults.value;
  if (!rows.length) return;
  const quote = (v: unknown) => {
    const text = String(v ?? "");
    // CSV 公式注入防护：Excel 会把 = + - @ 开头的内容当公式
    const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const header = ["书名", "结果", "书源", "匹配书名", "匹配作者", "分数", "说明", "时间"];
  const lines = [header.map(quote).join(",")];
  for (const r of rows) {
    lines.push(
      [
        r.title,
        batchActionLabel[r.action] || r.action,
        r.source || "",
        r.hit_title || "",
        r.hit_author || "",
        r.score != null ? r.score.toFixed(2) : "",
        r.message || "",
        r.time || "",
      ]
        .map(quote)
        .join(","),
    );
  }
  const blob = new Blob(["\uFEFF" + lines.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `scrape-report-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const kindLabel: Record<string, string> = {
  chapter_parse: "未分章",
  encoding: "乱码",
  control_chars: "控制符",
  empty_chapters: "空章节",
  source_missing: "缺源文件",
};

/** 异常类型筛选：只影响列表展示，"修复全部"仍处理所有异常书 */
const issueKindFilter = ref("all");
const issueKindOptions = computed(() => {
  const counts = new Map<string, number>();
  for (const it of report.value?.issues || []) {
    counts.set(it.kind, (counts.get(it.kind) || 0) + 1);
  }
  return [
    { kind: "all", label: "全部", count: report.value?.issues?.length || 0 },
    ...Object.entries(kindLabel).map(([kind, label]) => ({
      kind,
      label,
      count: counts.get(kind) || 0,
    })),
  ];
});
const filteredIssues = computed(() => {
  const issues = report.value?.issues || [];
  return issueKindFilter.value === "all"
    ? issues
    : issues.filter((it) => it.kind === issueKindFilter.value);
});

// 修复后当前类型已无异常时，自动回到"全部"，避免停留在空列表
watch(
  () => report.value?.issues,
  (issues) => {
    if (issueKindFilter.value === "all") return;
    if (!(issues || []).some((it) => it.kind === issueKindFilter.value)) {
      issueKindFilter.value = "all";
    }
  },
);

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
}

/** 启动后台体检（深度/快速），完成后从状态里取回报告 */
async function loadReport() {
  await refreshTasks();
  if (scanBlocked.value) {
    ElMessage.warning(`有「${scanBlocked.value}」任务进行中，请先等待完成`);
    return;
  }
  try {
    const res = await startScan(deepScan.value);
    scan.value = res.status;
    ElMessage.success(res.started ? "开始体检…" : "体检已在进行中");
    watchScan();
    void refreshTasks();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "启动体检失败");
  }
}

function stopScanWatch() {
  scanHandle?.close();
  scanHandle = null;
}

function onScanMessage(data: unknown) {
  const st = data as ScanStatus;
  scan.value = st;
  if (!st.running) {
    stopScanWatch();
    if (st.error) {
      ElMessage.error(`体检失败：${st.error}`);
    } else {
      if (st.report) check.setReport(st.report);
      ElMessage.success("体检完成");
    }
  }
}

function watchScan() {
  stopScanWatch();
  scanHandle = openSse(SCAN_STREAM_URL, onScanMessage, {
    shouldStop: (d) => !(d as ScanStatus).running,
    onFallback: () => {
      scanHandle = pollStatus(fetchScanStatus, onScanMessage, {
        shouldStop: (d) => !(d as ScanStatus).running,
      });
    },
  });
}

async function onCancelScan() {
  try {
    const res = await cancelScan();
    scan.value = res.status;
    ElMessage[res.ok ? "success" : "warning"](res.ok ? "已请求停止体检" : "当前没有进行中的体检");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "停止失败");
  }
}

async function refreshAll() {
  // 修复/合并后刷新书库并按当前深度档位重扫一次
  await Promise.all([lib.loadBooks(), lib.loadStats()]);
  await loadReport();
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

/** 只读预览后再执行修复，避免误重解析 */
async function openRepairPreview(ids: number[], title: string, mode = "auto") {
  if (!ids.length) {
    ElMessage.warning("没有需要修复的问题书");
    return;
  }
  const seq = ++repairPreviewSeq;
  repairPreviewIds = ids;
  repairPreviewMode = mode;
  repairPreviewTitle.value = title;
  repairPreviewItems.value = [];
  repairPreviewOpen.value = true;
  repairPreviewLoading.value = true;
  try {
    const res = await previewRepair(mode, ids);
    if (seq !== repairPreviewSeq) return;
    repairPreviewItems.value = res.items || [];
  } catch (e) {
    if (seq === repairPreviewSeq) {
      repairPreviewOpen.value = false;
      ElMessage.error(e instanceof Error ? e.message : "修复预览失败");
    }
  } finally {
    if (seq === repairPreviewSeq) repairPreviewLoading.value = false;
  }
}

async function executeRepair(ids: number[], mode: string) {
  acting.value = true;
  try {
    const res = await repairAll(mode, ids);
    ElMessage.success(`已修复 ${res.count || 0} 本`);
    await refreshAll();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "修复失败");
  } finally {
    acting.value = false;
  }
}

async function confirmRepairPreview() {
  const ids = [...repairPreviewIds];
  const mode = repairPreviewMode;
  repairPreviewOpen.value = false;
  await executeRepair(ids, mode);
}

async function onRepairOne(bookId: number) {
  const issue = report.value?.issues.find((it) => it.book_id === bookId);
  await openRepairPreview([bookId], `修复预览 · ${issue?.title || `#${bookId}`}`);
}

async function onRepairAll() {
  // 只修当前报告里已列出的问题书；后端要求显式 ids，避免隐式全库深扫
  const ids = [...new Set((report.value?.issues || []).map((i) => i.book_id))];
  if (!ids.length) {
    ElMessage.warning("没有需要修复的问题书");
    return;
  }
  await openRepairPreview(ids, `批量修复预览（${ids.length} 本）`);
}

async function onRebuildThumbs() {
  const limit = 200;
  try {
    await ElMessageBox.confirm(
      `为最多 ${limit} 本已有封面的书生成/更新缩略图？\n幂等执行，已是最新的会跳过；可重复点击继续处理。`,
      "重建缩略图",
      { type: "info", confirmButtonText: "开始", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  acting.value = true;
  try {
    const res = await rebuildThumbs({ limit });
    if (!res.available) {
      ElMessage.warning("未安装 Pillow，无法生成缩略图");
    } else if (!res.total) {
      ElMessage.info("没有需要处理的封面");
    } else if (res.failed) {
      ElMessage.warning(
        `缩略图：生成 ${res.generated} · 跳过 ${res.skipped} · 失败 ${res.failed}`,
      );
    } else {
      ElMessage.success(`缩略图完成：生成 ${res.generated} · 跳过 ${res.skipped}`);
    }
    await lib.loadBooks();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "重建缩略图失败");
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
  await refreshTasks();
  if (scrapeBlocked.value) {
    ElMessage.warning(`有「${scrapeBlocked.value}」任务进行中，请先等待完成`);
    return;
  }
  starting.value = true;
  batchActionFilter.value = "all";
  try {
    const res = await startBatchScrape({
      source: source.value,
      only_missing: onlyMissing.value,
      min_score: minScore.value,
      mode: scrapeMode.value,
    });
    batch.value = res.status;
    ElMessage.success(res.started ? "一键刮削已开始" : "批处理已在运行");
    watchBatch();
    void refreshTasks();
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
  // 报告缓存在 Pinia（内存态）；如后台体检在跑则恢复进度，否则沿用上次报告
  try {
    const st = await fetchScanStatus();
    scan.value = st;
    if (st.running) watchScan();
    else if (st.report) check.setReport(st.report);
  } catch {
    /* ignore */
  }
  await refreshTasks();
  tasksTimer = setInterval(refreshTasks, 3000);
  await onRefreshBatch();
});
onUnmounted(() => {
  stopWatch();
  stopScanWatch();
  if (tasksTimer) clearInterval(tasksTimer);
});
</script>

<template>
  <div v-loading="acting" class="page check-page">
    <header class="page-header">
      <div class="title-row">
        <h1 class="page-title">书库体检</h1>
        <span class="count-pill">{{ summary }}</span>
      </div>
      <div class="page-actions">
        <label class="check-label" title="读正文检查乱码/控制字符，书多时较慢">
          <input v-model="deepScan" type="checkbox" :disabled="!!scan?.running" />
          深度体检
        </label>
        <button
          type="button"
          class="ghost-btn"
          :disabled="!!scan?.running || !!scanBlocked"
          @click="loadReport"
        >
          <AppIcon name="refresh" :size="14" />
          {{
            scan?.running
              ? `扫描中 ${scanPercent}%`
              : scanBlocked
                ? `${scanBlocked}进行中`
                : scanned
                  ? "重新扫描"
                  : "开始扫描"
          }}
        </button>
        <button v-if="scan?.running" type="button" class="ghost-btn danger" @click="onCancelScan">
          停止扫描
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
        <button
          type="button"
          class="ghost-btn"
          title="为已有封面批量生成/更新缩略图（每次最多 200 本）"
          :disabled="acting"
          @click="onRebuildThumbs"
        >
          <AppIcon name="refresh" :size="14" />
          重建缩略图
        </button>
      </div>
      <p v-if="scanBlocked" class="muted check-hint">
        当前有「{{ scanBlocked }}」任务进行中，体检暂不可用（导入 / 体检 / 刮削互斥）。
      </p>
      <div v-if="scan?.running" class="scan-progress">
        <div class="progress-track">
          <div class="progress-bar" :style="{ width: scanPercent + '%' }" />
        </div>
        <span class="progress-label">{{ scanPercent }}%</span>
      </div>
      <p v-else-if="scan?.error" class="muted check-hint is-error">体检失败：{{ scan.error }}</p>
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
        <div v-if="!scanned" class="empty">
          <AppIcon name="check" :size="24" />
          <span>尚未扫描，点右上角「开始扫描」检查重复书。</span>
        </div>
        <div v-else-if="!report?.duplicates?.length" class="empty">
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
        <p class="muted">
          修复：清理控制字符；若源 TXT 仍可读且未分章/乱码，则重新解析章节。
          勾选「深度体检」可查乱码/控制符（需读正文，较慢）。
        </p>
        <div
          v-if="scanned && report?.issues?.length"
          class="filter-chips"
          role="group"
          aria-label="异常类型筛选"
        >
          <button
            v-for="opt in issueKindOptions"
            :key="opt.kind"
            type="button"
            class="filter-chip"
            :class="{ 'is-active': issueKindFilter === opt.kind }"
            :aria-pressed="issueKindFilter === opt.kind"
            @click="issueKindFilter = opt.kind"
          >
            {{ opt.label }}
            <span class="filter-count">{{ opt.count }}</span>
          </button>
        </div>
        <p v-if="scanned && issueKindFilter !== 'all'" class="muted-xs filter-hint">
          筛选只影响列表展示，「修复全部」仍处理所有异常书。
        </p>
        <div v-if="!scanned" class="empty">
          <AppIcon name="check" :size="24" />
          <span>尚未扫描，点右上角「开始扫描」检查异常书。</span>
        </div>
        <div v-else-if="!report?.issues?.length" class="empty">
          <AppIcon name="check" :size="24" />
          <span>没有发现异常，书库健康。</span>
        </div>
        <div v-else-if="!filteredIssues.length" class="empty">
          <AppIcon name="check" :size="24" />
          <span>当前筛选下没有异常。</span>
        </div>
        <div v-for="it in filteredIssues" :key="it.book_id + it.kind" class="check-item">
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
          选「全部」时按<strong>起点 → 番茄 → 纵横</strong>顺序，达到阈值即写入并停止，不再试后续书源。<br />
          刮削方式<strong>默认 API 直连</strong>；「自动」为 API 优先、失败再回退 Chrome；「Chrome」强制走浏览器（需环境支持）。
        </p>
        <div class="controls">
          <span class="label">刮削源</span>
          <select v-model="source" class="field-input">
            <option value="all">全部（顺序匹配）</option>
            <option value="qidian">起点</option>
            <option value="fanqie">番茄</option>
            <option value="zongheng">纵横</option>
          </select>
          <span class="label">刮削方式</span>
          <select v-model="scrapeMode" class="field-input" title="刮削取数方式">
            <option v-for="opt in SCRAPE_MODE_OPTS" :key="opt.value" :value="opt.value" :title="opt.hint">
              {{ opt.label }}
            </option>
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
          <button
            type="button"
            class="primary-btn"
            :disabled="starting || !!scrapeBlocked"
            @click="onStartBatch"
          >
            {{ starting ? "启动中…" : scrapeBlocked ? `${scrapeBlocked}进行中` : "开始一键刮削" }}
          </button>
          <button type="button" class="ghost-btn danger" @click="onCancelBatch">停止</button>
          <button type="button" class="ghost-btn" @click="onRefreshBatch">刷新进度</button>
        </div>
        <p v-if="scrapeBlocked" class="muted check-hint">
          当前有「{{ scrapeBlocked }}」任务进行中，刮削暂不可用（导入 / 体检 / 刮削互斥）。
        </p>

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

        <div v-if="batchResults.length" class="batch-report">
          <div class="batch-report-head">
            <h3 class="batch-report-title">
              刮削结果
              <span class="muted-xs">{{ batchResults.length }} 条</span>
            </h3>
            <button type="button" class="ghost-btn sm" @click="exportBatchReport">
              导出 CSV
            </button>
          </div>
          <div class="filter-chips" role="group" aria-label="刮削结果筛选">
            <button
              v-for="opt in batchActionOptions"
              :key="opt.action"
              type="button"
              class="filter-chip"
              :class="{ 'is-active': batchActionFilter === opt.action }"
              :aria-pressed="batchActionFilter === opt.action"
              @click="batchActionFilter = opt.action"
            >
              {{ opt.label }}
              <span class="filter-count">{{ opt.count }}</span>
            </button>
          </div>
          <div class="batch-table-wrap">
            <table class="batch-table">
              <thead>
                <tr>
                  <th>书名</th>
                  <th>结果</th>
                  <th>书源</th>
                  <th>匹配结果</th>
                  <th>分数</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in filteredBatchResults" :key="`${r.book_id}-${r.time}-${i}`">
                  <td class="batch-title" :title="r.title">{{ r.title || "—" }}</td>
                  <td>
                    <span class="tag-soft" :class="batchActionClass(r.action)">
                      {{ batchActionLabel[r.action] || r.action }}
                    </span>
                  </td>
                  <td :title="r.source_id || ''">{{ r.source || "—" }}</td>
                  <td class="batch-hit" :title="`${r.hit_title || ''} ${r.hit_author || ''}`">
                    {{ r.hit_title || "—" }}
                    <template v-if="r.hit_author"> · {{ r.hit_author }}</template>
                  </td>
                  <td class="num">{{ r.score != null ? r.score.toFixed(2) : "—" }}</td>
                  <td class="batch-msg" :title="r.message || ''">{{ r.message || "—" }}</td>
                </tr>
              </tbody>
            </table>
            <p v-if="!filteredBatchResults.length" class="muted batch-empty">
              当前筛选下没有结果。
            </p>
          </div>
        </div>

        <pre class="log-panel">{{ batchLog }}</pre>
      </div>
    </section>

    <el-dialog
      v-model="repairPreviewOpen"
      :title="repairPreviewTitle"
      width="min(640px, 92vw)"
      append-to-body
    >
      <div v-loading="repairPreviewLoading" class="repair-preview-body">
        <p class="muted repair-preview-hint">
          预览只读取书籍，不会修改；确认后才会执行修复。
        </p>
        <div v-if="repairPreviewItems.length" class="repair-preview-list">
          <div v-for="it in repairPreviewItems" :key="it.id" class="repair-preview-item">
            <div class="repair-preview-head">
              <span class="repair-preview-title">{{ it.title || `#${it.id}` }}</span>
              <span class="repair-preview-meta">
                <span>{{ it.chapter_count ?? "—" }} 章</span>
                <span v-if="it.new_chapter_count != null">→ {{ it.new_chapter_count }} 章</span>
                <span
                  v-if="it.need_reparse"
                  class="repair-source"
                  :class="{ 'is-error': it.source_available === false }"
                >
                  源文件{{ it.source_available ? "可读" : "不可用" }}
                </span>
              </span>
            </div>
            <div class="repair-preview-actions">
              <span
                v-for="(action, ai) in it.actions"
                :key="ai"
                class="tag-soft"
                :class="it.error ? 'is-danger' : it.will_change ? 'is-warning' : 'is-success'"
              >
                {{ action }}
              </span>
            </div>
            <p v-if="it.error" class="repair-preview-error">{{ it.error }}</p>
          </div>
        </div>
        <p v-else-if="!repairPreviewLoading" class="muted">没有可预览的书籍。</p>
      </div>
      <template #footer>
        <div class="repair-preview-footer">
          <button type="button" class="ghost-btn" @click="repairPreviewOpen = false">
            取消
          </button>
          <button
            type="button"
            class="primary-btn"
            :disabled="repairPreviewLoading || !repairPreviewActionable"
            @click="confirmRepairPreview"
          >
            确认修复
          </button>
        </div>
      </template>
    </el-dialog>
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

.check-hint {
  margin: 0;
}

.check-hint.is-error {
  color: var(--color-danger);
}

.scan-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
}

.scan-progress .progress-track {
  flex: 1;
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

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
}

.filter-chip:hover {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.filter-chip.is-active {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-weight: 600;
}

.filter-count {
  min-width: 16px;
  padding: 0 4px;
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.filter-chip.is-active .filter-count {
  background: var(--color-surface);
  color: var(--color-accent);
}

.filter-hint {
  margin: 0;
}

.batch-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
}

.batch-report-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.batch-report-title {
  margin: 0;
  font-size: var(--text-sm);
}

.batch-table-wrap {
  overflow: auto;
  max-height: 360px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.batch-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  font-size: var(--text-xs);
}

.batch-table th,
.batch-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}

.batch-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-weight: 600;
  white-space: nowrap;
}

.batch-table tbody tr:last-child td {
  border-bottom: none;
}

.batch-title {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-hit {
  max-width: 200px;
  color: var(--color-text-2);
}

.batch-msg {
  max-width: 260px;
  color: var(--color-text-3);
  word-break: break-word;
}

.batch-table .num {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.batch-empty {
  margin: 0;
  padding: 16px;
  text-align: center;
}

.repair-preview-body {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.repair-preview-hint {
  margin: 0;
}

.repair-preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50vh;
  overflow: auto;
}

.repair-preview-item {
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
}

.repair-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.repair-preview-title {
  font-weight: 600;
  font-size: var(--text-sm);
  word-break: break-word;
}

.repair-preview-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--color-text-3);
  font-size: var(--text-xs);
}

.repair-source.is-error {
  color: var(--color-danger);
}

.repair-preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.repair-preview-error {
  margin: 6px 0 0;
  color: var(--color-danger);
  font-size: var(--text-xs);
}

.repair-preview-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
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

@media (max-width: 576px) {
  .controls {
    flex-direction: column;
    align-items: stretch;
  }

  .controls .field-input,
  .controls .primary-btn,
  .controls .ghost-btn {
    width: 100%;
  }
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
