<script setup lang="ts">
/**
 * 书籍详情编辑：书名/作者/两级分类/状态/标签/简介、封面上传、删除、章节预览。
 */
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteBook, fetchBook, fetchStats, updateBook, uploadCover } from "@/api/admin";
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

const chaptersPreview = computed(() => book.value?.chapters_preview || []);

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

async function load() {
  if (!bookId.value) {
    ElMessage.error("无效的书籍 ID");
    return;
  }
  loading.value = true;
  try {
    const [detail, st] = await Promise.all([fetchBook(bookId.value), fetchStats()]);
    stats.value = st;
    applyBook(detail);
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
          阅读
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
        <p class="muted-xs">支持 jpg / png / webp / gif</p>

        <button type="button" class="ghost-btn block" @click="scrapeOpen = true">
          <AppIcon name="search" :size="14" />
          刮削元数据
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
        <div class="field">
          <label class="field-label">书名 <span class="req">*</span></label>
          <input v-model="form.title" class="field-input" maxlength="200" />
        </div>
        <div class="field">
          <label class="field-label">作者</label>
          <input v-model="form.author" class="field-input" maxlength="100" placeholder="佚名" />
        </div>

        <h2 class="section-title">分类与状态</h2>
        <div class="two-col">
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
        </div>
        <div class="field">
          <label class="field-label">状态</label>
          <select v-model="form.status" class="field-input">
            <option value="连载">连载</option>
            <option value="完结">完结</option>
            <option value="未知">未知</option>
          </select>
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
        <p class="muted-xs">保存时仍以逗号分隔写入，兼容原有字段。</p>

        <h2 class="section-title">简介</h2>
        <textarea v-model="form.intro" class="field-textarea" rows="8" />

        <h2 class="section-title">章节预览</h2>
        <div v-if="chaptersPreview.length" class="chapter-list">
          <div v-for="ch in chaptersPreview" :key="ch.id" class="chapter-row">
            <span class="idx muted-xs">{{ ch.index }}</span>
            <span class="ch-title">{{ ch.title }}</span>
          </div>
        </div>
        <p v-else class="muted">暂无章节预览。</p>
      </section>
    </div>

    <ScrapeDialog
      v-model:visible="scrapeOpen"
      :book-id="bookId"
      :local-name="form.title || book?.name || ''"
      :local-author="form.author || book?.author || ''"
      @applied="applyBook"
    />
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

.ghost-btn.block {
  width: 100%;
  justify-content: center;
}

.ghost-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--space-4);
  align-items: start;
}

/* 平板：封面栏收窄，保证表单可读宽度 */
@media (max-width: 1100px) {
  .layout {
    grid-template-columns: 200px 1fr;
  }
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .cover-side {
    position: static;
    max-width: 280px;
  }
}

.cover-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: sticky;
  top: 0;
}

.cover-img {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
}

.cover-placeholder {
  width: 100%;
  aspect-ratio: 3 / 4;
  border-radius: var(--radius-md);
  background: linear-gradient(160deg, var(--color-surface-2), var(--color-surface-3));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-3);
  text-align: center;
  padding: 12px;
  word-break: break-all;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--color-text-2);
}

.upload-label:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
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
  gap: 4px;
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
  max-height: 36px;
  overflow: hidden;
}

.path.is-open {
  max-height: none;
}

.section-title {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--text-base);
  font-weight: 600;
}

.section-title:first-child {
  margin-top: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: var(--space-3);
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
  height: 36px;
  padding: 0 12px;
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
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: inherit;
  line-height: 1.65;
  resize: vertical;
  outline: none;
}

.field-textarea:focus {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
  background: var(--color-surface);
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
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
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  min-height: 40px;
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
</style>
