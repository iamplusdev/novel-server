<script setup lang="ts">
/**
 * 单本刮削弹窗：搜索 / 按书号拉详情 / 核对后写入。
 * emits: applied —— 写入成功后由父组件刷新表单
 */
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  SCRAPE_SOURCE_OPTS,
  cleanHintTags,
  looksLikeBookId,
  scrapeApply,
  scrapeDetail,
  scrapeSearch,
} from "@/api/scrape";
import type { BookDetail, ScrapeHit } from "@/api/types";

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
      const hit = await scrapeDetail({ source: source.value, source_book_id: kw });
      items.value = [{ ...hit, source_id: hit.source_id || kw }];
    } else {
      tip.value = "正在搜索…";
      const res = await scrapeSearch({ keyword: kw, source: source.value, limit: 10 });
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
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="刮削元数据"
    width="640px"
    :close-on-click-modal="false"
  >
    <div class="search-row">
      <el-input
        v-model="keyword"
        placeholder="书名 / 书号 / 详情链接"
        @keyup.enter="runSearch"
      />
      <el-select v-model="source" style="width: 110px">
        <el-option
          v-for="opt in SCRAPE_SOURCE_OPTS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-button type="primary" :loading="loading" @click="runSearch">搜索</el-button>
    </div>

    <p class="muted tip">{{ tip }}</p>

    <div class="local muted">
      本地：<strong>{{ localName }}</strong>
      <template v-if="localAuthor"> · {{ localAuthor }}</template>
    </div>

    <div v-loading="loading || applying" class="results">
      <el-empty v-if="!items.length" description="暂无结果" :image-size="60" />
      <div v-for="(hit, i) in items" :key="hit.source_id || i" class="hit-card">
        <img
          v-if="hit.cover_url"
          :src="hit.cover_url"
          alt=""
          class="hit-cover"
        />
        <div class="hit-body">
          <div class="hit-title">{{ hit.name || "（无书名）" }}</div>
          <div class="muted">{{ hit.author || "佚名" }} · {{ hit.status || "—" }}</div>
          <div class="muted">
            {{ hit.category || "" }}
            <template v-if="hit.word_count"> · {{ hit.word_count }} 字</template>
            <template v-if="hit.latest_chapter"> · 最新 {{ hit.latest_chapter }}</template>
          </div>
          <div class="muted mono">ID {{ hit.source_id }} · {{ hit.source }}</div>
        </div>
        <el-button type="primary" size="small" :loading="applying" @click="askAndApply(hit)">
          采用并写入
        </el-button>
      </div>
    </div>

    <template #footer>
      <el-button @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.search-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.tip {
  margin: 0 0 8px;
}

.local {
  margin-bottom: 10px;
}

.results {
  min-height: 120px;
  max-height: 420px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hit-card {
  display: flex;
  gap: 10px;
  align-items: center;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 10px;
}

.hit-cover {
  width: 52px;
  height: 70px;
  object-fit: cover;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  flex-shrink: 0;
}

.hit-body {
  flex: 1;
  min-width: 0;
}

.hit-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.mono {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
}
</style>
