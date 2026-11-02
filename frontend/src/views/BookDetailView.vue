<script setup lang="ts">
/**
 * 书籍详情编辑：书名/作者/两级分类/状态/标签/简介、封面上传、删除、章节预览。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteBook,
  fetchAllBookChapters,
  fetchBook,
  fetchStats,
  fetchSyncInfo,
  isTocPlaceholder,
  pullBookProgress,
  pushBookProgressNow,
  updateBook,
  uploadCover,
} from "@/api/admin";
import type { SyncInfo, TocChapter } from "@/api/admin";
import ScrapeDialog from "@/components/ScrapeDialog.vue";
import AppIcon from "@/components/AppIcon.vue";
import type { AdminStats, BookDetail } from "@/api/types";

const route = useRoute();
const router = useRouter();

const book = ref<BookDetail | null>(null);
const stats = ref<AdminStats | null>(null);
const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const coverUploading = ref(false);

const form = reactive({
  title: "",
  author: "",
  category_source: "",
  category_name: "",
  status: "未知",
  tags: "",
  intro: "",
});

const coverPreview = ref("");
const coverFile = ref<File | null>(null);
const scrapeOpen = ref(false);
const pathExpanded = ref(false);

// WebDAV 进度同步：详情页诊断 + 手动拉取/推送
const syncOpen = ref(false);
const syncLoading = ref(false);
const syncInfo = ref<SyncInfo | null>(null);
const syncPulling = ref(false);
const syncPushing = ref(false);

const bookId = computed(() => {
  const raw = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id;
  const n = Number.parseInt(String(raw ?? ""), 10);
  return Number.isInteger(n) && n > 0 ? n : 0;
});

const sourceOptions = computed(() => {
  const tree = stats.value?.category_tree || [];
  return tree.map((n) => ({ value: n.key, label: n.label }));
});

const categoryOptions = computed(() => {
  const tree = stats.value?.category_tree || [];
  const node = tree.find((n) => n.key === form.category_source);
  return node ? node.categories : [];
});

const tagList = computed(() =>
  form.tags
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean),
);

/** 当前阅读进度摘要 */
const readLabel = computed(() => {
  const b = book.value;
  if (!b?.read_at) return "未读";
  const percent = Number(b.read_percent ?? 0);
  const chapter = Number(b.read_chapter_index ?? -1);
  return [
    percent >= 100 ? "已读完" : `已读 ${percent}%`,
    chapter >= 0 ? `第 ${chapter + 1} 章` : "",
    b.read_at,
  ]
    .filter(Boolean)
    .join(" · ");
});

/** 完整目录（下方栏） */
const tocItems = ref<TocChapter[]>([]);
const tocTotal = ref(0);
const tocLoading = ref(false);

/** 目录分页：每 200 章一段；'all' 为全部滚动 */
const TOC_PAGE_SIZE = 200;
const tocPage = ref<number | "all">("all");
const tocFilter = ref("");

/** 目录展示项：过滤伪占位行后附带 1 基顺序序号 */
type TocDisplayItem = TocChapter & { no: number };

const displayTocItems = computed<TocDisplayItem[]>(() => {
  const bookName = form.title || book.value?.name;
  const named = tocItems.value.filter((c) => !isTocPlaceholder(c.title, bookName));
  return named.map((c, i) => ({ ...c, no: i + 1 }));
});

const filterActive = computed(() => tocFilter.value.trim().length > 0);

/** 目录筛选结果：标题或章节序号 */
const filteredTocItems = computed(() => {
  const kw = tocFilter.value.trim().toLowerCase();
  if (!kw) return displayTocItems.value;
  return displayTocItems.value.filter(
    (c) => c.title.toLowerCase().includes(kw) || String(c.no) === kw,
  );
});

const tocPageRanges = computed(() => {
  if (filterActive.value) return [];
  const total = displayTocItems.value.length || tocTotal.value;
  const pages: { key: number; label: string }[] = [];
  if (total <= TOC_PAGE_SIZE) return pages;
  for (let start = 1; start <= total; start += TOC_PAGE_SIZE) {
    const end = Math.min(start + TOC_PAGE_SIZE - 1, total);
    pages.push({ key: start, label: `${start}–${end}` });
  }
  return pages;
});

/** 页签条横向滚动（章节极多时避免铺满换行） */
const tocPagesTrack = ref<HTMLElement | null>(null);
const tocScrollLeft = ref(false);
const tocScrollRight = ref(false);

/** 页签较多时才显示左右按钮 */
const showTocNav = computed(() => tocPageRanges.value.length > 3);

function updateTocScrollState() {
  const el = tocPagesTrack.value;
  if (!el) {
    tocScrollLeft.value = false;
    tocScrollRight.value = false;
    return;
  }
  const max = el.scrollWidth - el.clientWidth;
  tocScrollLeft.value = el.scrollLeft > 1;
  tocScrollRight.value = el.scrollLeft < max - 1;
}

function scrollTocPages(dir: -1 | 1) {
  const el = tocPagesTrack.value;
  if (!el) return;
  el.scrollBy({ left: dir * Math.max(el.clientWidth * 0.6, 120), behavior: "smooth" });
}

function scrollTocIntoView() {
  const el = tocPagesTrack.value;
  if (!el) return;
  const active = el.querySelector<HTMLElement>(".page-chip.is-active");
  if (active) {
    const left = active.offsetLeft - el.clientWidth / 2 + active.offsetWidth / 2;
    el.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  }
  // 滚动动画结束后刷新按钮态
  window.setTimeout(updateTocScrollState, 280);
}

watch(
  tocPage,
  () => {
    nextTick(() => {
      scrollTocIntoView();
    });
  },
  { flush: "post" },
);

onMounted(() => {
  nextTick(() => {
    updateTocScrollState();
  });
  window.addEventListener("resize", updateTocScrollState);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateTocScrollState);
});

const visibleTocItems = computed(() => {
  if (filterActive.value) return filteredTocItems.value;
  if (tocPage.value === "all") return displayTocItems.value;
  const start = Number(tocPage.value);
  const end = start + TOC_PAGE_SIZE - 1;
  // 页签按过滤后的 1 基展示序号分页
  return displayTocItems.value.filter((c) => c.no >= start && c.no <= end);
});

function applyBook(b: BookDetail) {
  book.value = b;
  form.title = b.name || "";
  form.author = b.author || "";
  form.category_source = b.category_source ?? "";
  form.category_name = b.category_name ?? "";
  form.status = b.status || "未知";
  form.tags = Array.isArray(b.tags) ? b.tags.join(", ") : b.tags || "";
  form.intro = b.intro || "";
  coverPreview.value = b.cover_url || b.cover_path || "";
  coverFile.value = null;
  // 分类不在下拉里时补入，避免刮削结果被显示成空
  const tree = stats.value?.category_tree;
  if (tree && form.category_name) {
    const node = tree.find((n) => n.key === form.category_source);
    if (node && !node.categories.includes(form.category_name)) {
      node.categories = [...node.categories, form.category_name];
    }
  }
}

async function loadToc() {
  if (!bookId.value) return;
  tocLoading.value = true;
  try {
    const { items, total } = await fetchAllBookChapters(bookId.value);
    tocItems.value = items;
    tocTotal.value = total || items.length || book.value?.chapter_count || 0;
  } catch {
    tocItems.value = (book.value?.chapters_preview || []).map((c) => ({
      id: c.id,
      index: c.index,
      title: c.title,
    }));
    tocTotal.value = book.value?.chapter_count || tocItems.value.length;
    // 页签条出现后刷新左右按钮可用态
    nextTick(() => {
      updateTocScrollState();
      scrollTocIntoView();
    });
  } finally {
    tocLoading.value = false;
  }
}

async function load() {
  if (!bookId.value) {
    ElMessage.error("无效的书籍 ID");
    return;
  }
  tocFilter.value = "";
  loading.value = true;
  try {
    const [detail, st] = await Promise.all([fetchBook(bookId.value), fetchStats()]);
    stats.value = st;
    applyBook(detail);
    void loadToc();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}

function onSourceChange() {
  // 换书源后站内分类重置为该源第一项
  const opts = categoryOptions.value;
  form.category_name = opts[0] || "未分类";
}

function onCoverPick(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  coverFile.value = file;
  // 本地预览
  const reader = new FileReader();
  reader.onload = () => {
    coverPreview.value = String(reader.result || "");
  };
  reader.readAsDataURL(file);
}

function removeTag(tag: string) {
  form.tags = tagList.value.filter((t) => t !== tag).join(", ");
}

function addTagFromEnter(e: KeyboardEvent) {
  const input = e.target as HTMLInputElement;
  const val = input.value.trim();
  if (!val) return;
  if (!tagList.value.includes(val)) {
    form.tags = [...tagList.value, val].join(", ");
  }
  input.value = "";
}

async function copyPath() {
  const p = book.value?.source_path;
  if (!p) return;
  try {
    await navigator.clipboard.writeText(p);
    ElMessage.success("路径已复制");
  } catch {
    ElMessage.warning("复制失败");
  }
}

async function save() {
  if (!book.value) return;
  if (!form.title.trim()) {
    ElMessage.warning("请填写书名");
    return;
  }
  saving.value = true;
  try {
    if (coverFile.value) {
      coverUploading.value = true;
      await uploadCover(book.value.id, coverFile.value);
      coverUploading.value = false;
    }
    const updated = await updateBook(book.value.id, {
      title: form.title.trim(),
      author: form.author.trim() || "佚名",
      category_source: form.category_source,
      category_name: form.category_name,
      status: form.status,
      tags: form.tags,
      intro: form.intro,
    });
    applyBook(updated);
    ElMessage.success("已保存");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
    coverUploading.value = false;
  }
}

async function remove() {
  if (!book.value) return;
  const name = form.title || book.value.name;
  try {
    await ElMessageBox.confirm(
      `确认删除《${name}》？章节与封面将一并删除，源 TXT 文件保留。`,
      "删除书籍",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  deleting.value = true;
  try {
    await deleteBook(book.value.id);
    ElMessage.success(`已删除《${name}》`);
    router.push({ name: "library" });
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "删除失败");
  } finally {
    deleting.value = false;
  }
}

async function loadSyncInfo() {
  if (!bookId.value) return;
  syncLoading.value = true;
  try {
    syncInfo.value = await fetchSyncInfo(bookId.value);
  } catch (e) {
    syncInfo.value = null;
    ElMessage.error(e instanceof Error ? e.message : "读取同步状态失败");
  } finally {
    syncLoading.value = false;
  }
}

async function openSync() {
  syncOpen.value = true;
  await loadSyncInfo();
}

async function pullSync() {
  if (!bookId.value || syncPulling.value) return;
  syncPulling.value = true;
  try {
    const r = await pullBookProgress(bookId.value);
    if (r.updated) {
      ElMessage.success(`已拉取远端进度：第 ${(r.chapter_index ?? 0) + 1} 章`);
      try {
        // 只刷新书籍元信息，不覆盖表单里尚未保存的编辑
        book.value = await fetchBook(bookId.value);
      } catch {
        /* ignore */
      }
    } else if (!r.enabled) {
      ElMessage.warning("WebDAV 同步未启用");
    } else if (r.error) {
      ElMessage.error(r.error);
    } else if (r.found) {
      ElMessage.info(r.reason ? `未更新：${r.reason}` : "远端进度未更新");
    } else {
      ElMessage.info(`未找到远程文件：${r.filename || ""}`);
    }
    await loadSyncInfo();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "拉取失败");
  } finally {
    syncPulling.value = false;
  }
}

async function pushSync() {
  if (!bookId.value || syncPushing.value) return;
  syncPushing.value = true;
  try {
    const r = await pushBookProgressNow(bookId.value);
    if (r.pushed) {
      ElMessage.success("已推送本地进度到 WebDAV");
    } else if (r.skipped === "remote_newer") {
      ElMessage.warning("远端进度更新，已跳过本次推送");
    } else {
      ElMessage.error(r.error || "推送失败（本地可能还没有阅读进度）");
    }
    await loadSyncInfo();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "推送失败");
  } finally {
    syncPushing.value = false;
  }
}

/** 远程文件名解码后展示；复制时仍使用原始编码名 */
function displayFilename(name?: string): string {
  if (!name) return "—";
  try {
    return decodeURIComponent(name);
  } catch {
    return name;
  }
}

async function copyFilename() {
  const name = syncInfo.value?.filename;
  if (!name) return;
  try {
    await navigator.clipboard.writeText(name);
    ElMessage.success("原始文件名已复制");
  } catch {
    ElMessage.warning("复制失败");
  }
}

function formatSyncTime(ms?: number): string {
  if (!ms) return "—";
  const d = new Date(ms);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function localProgressText(info: SyncInfo | null): string {
  if (!info) return "—";
  const idx = info.local.read_chapter_index;
  const base = idx >= 0 ? `第 ${idx + 1} 章 · ${info.local.read_percent}%` : "未读";
  return info.local.read_at ? `${base} · ${info.local.read_at}` : base;
}

function fmtWords(n?: number) {
  if (n === undefined || n === null) return "—";
  if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return String(n);
}

function openReader() {
  if (!bookId.value) return;
  router.push({ name: "book-read", params: { id: String(bookId.value) } });
}

/** 从目录进入阅读器并定位到该章 */
function openReaderAt(ch: TocChapter) {
  if (!bookId.value) return;
  router.push({
    name: "book-read",
    params: { id: String(bookId.value) },
    query: { chapter: String(ch.id) },
  });
}

onMounted(load);
watch(bookId, () => void load());
</script>

<template>
  <div v-loading="loading" class="page detail-page">
    <header class="page-header">
      <div class="title-row">
        <button type="button" class="back-btn" @click="router.push({ name: 'library' })">
          <AppIcon name="back" :size="18" />
          <span>书库</span>
        </button>
        <h1 class="page-title">{{ form.title || "书籍详情" }}</h1>
      </div>
      <div class="page-actions">
        <button type="button" class="ghost-btn" @click="openReader">
          <AppIcon name="book" :size="16" />
          {{ book?.read_at ? "继续阅读" : "阅读" }}
        </button>
        <button type="button" class="ghost-btn danger" :disabled="deleting" @click="remove">
          <AppIcon name="trash" :size="16" />
          删除
        </button>
        <button type="button" class="primary-btn" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存" }}
        </button>
      </div>
    </header>

    <div class="layout">
      <!-- 上：封面 | 基础信息 -->
      <div class="top-row">
        <aside class="cover-side page-card">
          <img
            v-if="coverPreview"
            :src="coverPreview"
            alt="封面"
            class="cover-img"
          />
          <div v-else class="cover-placeholder">{{ form.title || "无封面" }}</div>

          <label class="upload-label">
            <AppIcon name="plus" :size="14" />
            上传封面
            <input type="file" accept="image/*" hidden @change="onCoverPick" />
          </label>
          <p class="muted-xs cover-hint">jpg / png / webp / gif</p>

          <button type="button" class="ghost-btn block" @click="scrapeOpen = true">
            <AppIcon name="search" :size="14" />
            刮削元数据
          </button>
          <button type="button" class="ghost-btn block" @click="openSync">
            <AppIcon name="api" :size="14" />
            进度同步
          </button>

          <div class="meta-block">
            <div class="meta-row">
              <span class="label">来源</span>
              <span class="value">
                {{ book?.source || "—" }}
                <template v-if="book?.source_id"> · {{ book.source_id }}</template>
              </span>
            </div>
            <div class="meta-row">
              <span class="label">字数</span>
              <span class="value">{{ fmtWords(book?.word_count) }}</span>
            </div>
            <div class="meta-row">
              <span class="label">章节</span>
              <span class="value">{{ book?.chapter_count ?? "—" }}</span>
            </div>
            <div class="meta-row">
              <span class="label">阅读</span>
              <span class="value">{{ readLabel }}</span>
            </div>
            <div v-if="book?.source_path" class="path-block">
              <div class="path-head">
                <span class="label">文件路径</span>
                <button type="button" class="link-btn" @click="copyPath">复制</button>
                <button type="button" class="link-btn" @click="pathExpanded = !pathExpanded">
                  {{ pathExpanded ? "收起" : "展开" }}
                </button>
              </div>
              <div class="path mono" :class="{ 'is-open': pathExpanded }" :title="book.source_path">
                {{ book.source_path }}
              </div>
            </div>
          </div>
        </aside>

        <section class="form-side page-card">
          <h2 class="section-title">基础信息</h2>
          <div class="two-col">
            <div class="field">
              <label class="field-label">书名 <span class="req">*</span></label>
              <input v-model="form.title" class="field-input" maxlength="200" />
            </div>
            <div class="field">
              <label class="field-label">作者</label>
              <input v-model="form.author" class="field-input" maxlength="100" placeholder="佚名" />
            </div>
          </div>
          <div class="three-col">
            <div class="field">
              <label class="field-label">书源</label>
              <select v-model="form.category_source" class="field-input" @change="onSourceChange">
                <option v-for="opt in sourceOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">分类</label>
              <select v-model="form.category_name" class="field-input">
                <option v-for="c in categoryOptions" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">状态</label>
              <select v-model="form.status" class="field-input">
                <option value="连载">连载</option>
                <option value="完结">完结</option>
                <option value="未知">未知</option>
              </select>
            </div>
          </div>

          <h2 class="section-title">标签</h2>
          <div class="tags-editor">
            <span v-for="t in tagList" :key="t" class="tag-soft is-accent tag-item">
              {{ t }}
              <button type="button" class="tag-x" aria-label="移除" @click="removeTag(t)">×</button>
            </span>
            <input
              class="tag-input"
              placeholder="输入后回车添加"
              @keyup.enter="addTagFromEnter"
            />
          </div>

          <h2 class="section-title">简介</h2>
          <textarea v-model="form.intro" class="field-textarea" rows="4" />
        </section>
      </div>

      <!-- 下：目录（200 章分页 / 全部滚动） -->
      <aside class="toc-side page-card">
        <div class="toc-side-head">
          <h2 class="section-title">目录</h2>
          <div v-if="!filterActive" class="toc-pages">
            <button
              type="button"
              class="page-chip"
              :class="{ 'is-active': tocPage === 'all' }"
              @click="tocPage = 'all'"
            >
              全部
            </button>
            <button
              v-if="showTocNav"
              type="button"
              class="page-nav-btn"
              :disabled="!tocScrollLeft"
              title="向前翻页"
              aria-label="向前翻页"
              @click="scrollTocPages(-1)"
            >
              ‹
            </button>
            <div ref="tocPagesTrack" class="toc-pages-track" @scroll.passive="updateTocScrollState">
              <button
                v-for="p in tocPageRanges"
                :key="p.key"
                type="button"
                class="page-chip"
                :class="{ 'is-active': tocPage === p.key }"
                @click="tocPage = p.key"
              >
                {{ p.label }}
              </button>
            </div>
            <button
              v-if="showTocNav"
              type="button"
              class="page-nav-btn"
              :disabled="!tocScrollRight"
              title="向后翻页"
              aria-label="向后翻页"
              @click="scrollTocPages(1)"
            >
              ›
            </button>
          </div>
          <span class="muted-xs toc-count">共 {{ tocTotal || book?.chapter_count || 0 }} 章</span>
        </div>
        <div class="toc-filter">
          <input v-model="tocFilter" class="toc-filter-input" placeholder="筛选章节…" />
          <button
            v-if="tocFilter"
            type="button"
            class="toc-clear"
            title="清除筛选"
            @click="tocFilter = ''"
          >
            ×
          </button>
          <span v-if="filterActive" class="muted-xs">{{ filteredTocItems.length }} 章</span>
        </div>
        <div v-loading="tocLoading" class="toc-side-list">
          <button
            v-for="ch in visibleTocItems"
            :key="ch.id"
            type="button"
            class="toc-side-item"
            @click="openReaderAt(ch)"
          >
            <span class="idx muted-xs">{{ ch.no }}</span>
            <span class="ch-title">{{ ch.title }}</span>
          </button>
          <p v-if="!visibleTocItems.length && !tocLoading" class="muted">
            {{ filterActive ? "没有匹配章节。" : "暂无章节。" }}
          </p>
        </div>
      </aside>
    </div>

    <ScrapeDialog
      v-model:visible="scrapeOpen"
      :book-id="bookId"
      :local-name="form.title || book?.name || ''"
      :local-author="form.author || book?.author || ''"
      @applied="applyBook"
    />

    <!-- WebDAV 进度同步诊断与手动操作 -->
    <el-dialog v-model="syncOpen" title="WebDAV 进度同步" width="560px" append-to-body>
      <div v-loading="syncLoading" class="sync-panel">
        <div class="sync-row">
          <span class="sync-label">本地进度</span>
          <span class="sync-value">{{ localProgressText(syncInfo) }}</span>
        </div>
        <div class="sync-row">
          <span class="sync-label">远程文件名</span>
          <span class="sync-value mono" :title="syncInfo?.filename || ''">
            {{ displayFilename(syncInfo?.filename) }}
          </span>
          <button
            v-if="syncInfo?.filename"
            type="button"
            class="link-btn sync-copy"
            @click="copyFilename"
          >
            复制
          </button>
        </div>
        <div class="sync-row">
          <span class="sync-label">远端状态</span>
          <span class="sync-value">
            <template v-if="!syncInfo?.configured">未启用 WebDAV</template>
            <template v-else-if="!syncInfo?.remote_exists">
              文件不存在（Legado 尚未上传该书）
            </template>
            <template v-else-if="syncInfo?.remote">
              第 {{ syncInfo.remote.durChapterIndex + 1 }} 章 ·
              {{ syncInfo.remote.durChapterTitle || "—" }} ·
              {{ formatSyncTime(syncInfo.remote.durChapterTime) }}
            </template>
            <template v-else>无法解析</template>
          </span>
        </div>
        <div class="sync-row">
          <span class="sync-label">匹配章节</span>
          <span class="sync-value">
            {{
              syncInfo?.matched
                ? `第 ${syncInfo.matched.index + 1} 章 · ${syncInfo.matched.title}`
                : "—"
            }}
          </span>
        </div>
        <p v-if="syncInfo?.error" class="sync-error">{{ syncInfo.error }}</p>
        <p class="muted-xs">
          拉取按 durChapterTime 最新者优先，章节标题优先匹配；推送使用本地章节序号。
        </p>
        <div class="sync-actions">
          <button type="button" class="ghost-btn" :disabled="syncLoading" @click="loadSyncInfo">
            刷新
          </button>
          <button type="button" class="primary-btn" :disabled="syncPulling" @click="pullSync">
            {{ syncPulling ? "拉取中…" : "拉取远端" }}
          </button>
          <button type="button" class="ghost-btn" :disabled="syncPushing" @click="pushSync">
            {{ syncPushing ? "推送中…" : "推送本地" }}
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
}

.back-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border-strong);
}

.page-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.primary-btn {
  height: 32px;
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

.ghost-btn:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.ghost-btn.danger {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.ghost-btn.block {
  width: 100%;
  justify-content: center;
}

.ghost-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.detail-page {
  /* 一屏装下：扣掉顶栏/内边距；页面自身不滚动，仅目录与卡片内滚动 */
  height: calc(100dvh - var(--header-h) - var(--space-5) * 2);
  min-height: 520px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  gap: var(--space-2);
}

.layout {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  min-height: 0;
}

.top-row {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: var(--space-3);
  align-items: stretch;
  /* 上排完整展示且不撑出一屏；高度随内容，尽量压缩 */
  flex-shrink: 0;
  max-height: 52%;
}

@media (max-width: 900px) {
  .detail-page {
    height: auto;
    min-height: calc(100dvh - var(--header-h) - var(--space-4) * 2);
    overflow: visible;
  }

  .top-row {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
  }

  .cover-side {
    max-width: 280px;
    overflow: visible;
    height: auto;
  }

  .form-side {
    overflow: visible;
    height: auto;
  }

  .toc-side {
    min-height: 240px;
    overflow: hidden;
  }
}

.toc-side {
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* 目录吃满剩余高度，仅列表内滚动（页面无滚动条） */
  flex: 1;
  overflow: hidden;
}

.toc-side-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 8px;
}

.toc-side-head .section-title {
  margin: 0;
}

.toc-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
}

.toc-filter-input {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: var(--text-xs);
  font-family: inherit;
  outline: none;
}

.toc-filter-input:focus {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
  background: var(--color-surface);
}

.toc-clear {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-3);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.toc-clear:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
}

.toc-pages {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.toc-pages-track {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  overflow-x: auto;
  overflow-y: hidden;
  min-width: 0;
  flex: 1;
  padding: 2px 0;
  scrollbar-width: none;
  -ms-overflow-style: none;
  scroll-behavior: smooth;
}

.toc-pages-track::-webkit-scrollbar {
  display: none;
}

.page-chip {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-2);
  font-size: var(--text-xs);
  padding: 3px 10px;
  border-radius: var(--radius-full);
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
  white-space: nowrap;
}

.page-nav-btn {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-2);
  border-radius: var(--radius-full);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: inherit;
  padding: 0;
}

.page-nav-btn:hover:not(:disabled) {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.page-nav-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.page-chip:hover {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.page-chip.is-active {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.toc-count {
  flex-shrink: 0;
}

.toc-side-list {
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  flex: 1;
  /* 细滚动条，长目录可滚 */
  scrollbar-width: thin;
  scrollbar-color: var(--color-border-strong) transparent;
  padding-right: 4px;
}

.toc-side-list::-webkit-scrollbar {
  width: 6px;
}

.toc-side-list::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
  border-radius: 3px;
}

.toc-side-list::-webkit-scrollbar-track {
  background: transparent;
}

.toc-side-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font: inherit;
  color: var(--color-text);
}

.toc-side-item:hover {
  background: var(--color-surface-2);
  color: var(--color-accent);
}

.toc-side-item .idx {
  flex-shrink: 0;
  min-width: 2.2em;
  text-align: right;
}

.toc-side-item .ch-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}

.cover-side {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  /* 内容超出时卡片内滚动，避免被裁剪不可达 */
  overflow: auto;
}

.cover-side .meta-block {
  margin-top: auto;
}

.form-side {
  min-width: 0;
  min-height: 0;
  /* 基础信息超出时卡片内滚动，避免被裁剪不可达 */
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.cover-img {
  width: 100%;
  aspect-ratio: 3 / 4;
  height: auto;
  object-fit: cover;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  flex-shrink: 0;
}

.cover-placeholder {
  width: 100%;
  aspect-ratio: 3 / 4;
  height: auto;
  border-radius: var(--radius-md);
  background: linear-gradient(160deg, var(--color-surface-2), var(--color-surface-3));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-3);
  text-align: center;
  padding: 12px;
  word-break: break-all;
  flex-shrink: 0;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  cursor: pointer;
  font-size: var(--text-xs);
  color: var(--color-text-2);
  flex-shrink: 0;
}

.upload-label:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.cover-hint {
  margin: 0;
  flex-shrink: 0;
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: var(--text-xs);
}

.meta-row .label {
  color: var(--color-text-3);
}

.meta-row .value {
  color: var(--color-text-2);
  text-align: right;
  word-break: break-all;
}

.path-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.path-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-xs);
}

.path-head .label {
  color: var(--color-text-3);
  flex: 1;
}

.link-btn {
  border: none;
  background: none;
  color: var(--color-accent);
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}

.path {
  font-size: 11px;
  color: var(--color-text-3);
  word-break: break-all;
  max-height: 28px;
  overflow: hidden;
}

.path.is-open {
  max-height: 36px;
  overflow: auto;
}

.section-title {
  margin: 10px 0 6px;
  font-size: var(--text-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.section-title:first-child {
  margin-top: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.field-label {
  font-size: var(--text-xs);
  color: var(--color-text-2);
  font-weight: 500;
}

.req {
  color: var(--color-danger);
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
  outline: none;
}

.field-input:focus {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
  background: var(--color-surface);
}

.field-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  outline: none;
  flex: 1;
  min-height: 64px;
  max-height: 120px;
}

.field-textarea:focus {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
  background: var(--color-surface);
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.three-col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}

@media (max-width: 576px) {
  .three-col {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 576px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}

.tags-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  min-height: 34px;
  flex-shrink: 0;
  max-height: 64px;
  overflow: hidden;
}

.tag-item {
  gap: 4px;
}

.tag-x {
  border: none;
  background: none;
  color: inherit;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
  opacity: 0.7;
}

.tag-x:hover {
  opacity: 1;
}

.tag-input {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
  height: 24px;
}

.chapter-list {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  max-height: 240px;
  overflow: auto;
}

.chapter-row {
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--text-sm);
}

.chapter-row:last-child {
  border-bottom: none;
}

.chapter-row:hover {
  background: var(--color-surface-2);
}

.idx {
  width: 32px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.ch-title {
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- WebDAV 进度同步弹窗 ---- */
.sync-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 120px;
}

.sync-row {
  display: flex;
  gap: 12px;
  font-size: var(--text-sm);
}

.sync-label {
  width: 84px;
  flex-shrink: 0;
  color: var(--color-text-3);
}

.sync-value {
  color: var(--color-text);
  word-break: break-all;
}

.sync-value.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: var(--text-xs);
}

.sync-copy {
  flex-shrink: 0;
  margin-left: auto;
}

.sync-error {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--text-xs);
}

.sync-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}
</style>
