<script setup lang="ts">
/**
 * 书籍详情编辑：书名/作者/两级分类/状态/标签/简介、封面上传、删除。
 */
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteBook, fetchBook, fetchStats, updateBook, uploadCover } from "@/api/admin";
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

const bookId = computed(() => String(route.params.id || ""));

const sourceOptions = computed(() => {
  const tree = stats.value?.category_tree || [];
  return tree.map((n) => ({ value: n.key, label: n.label }));
});

const categoryOptions = computed(() => {
  const tree = stats.value?.category_tree || [];
  const node = tree.find((n) => n.key === form.category_source);
  return node ? node.categories : [];
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
}

async function load() {
  if (!bookId.value) return;
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

onMounted(load);
watch(bookId, () => void load());
</script>

<template>
  <div v-loading="loading" class="detail-page">
    <header class="toolbar">
      <div class="toolbar-left">
        <el-button text @click="router.push({ name: 'library' })">← 返回书库</el-button>
        <h2>{{ form.title || "书籍详情" }}</h2>
      </div>
      <div class="toolbar-right">
        <el-button type="danger" plain :loading="deleting" @click="remove">删除书籍</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </header>

    <div class="layout">
      <div class="cover-side page-card">
        <img
          v-if="coverPreview"
          :src="coverPreview"
          alt="封面"
          class="cover-img"
        />
        <div v-else class="cover-placeholder">{{ form.title || "无封面" }}</div>
        <label class="upload-label">
          上传封面
          <input type="file" accept="image/*" hidden @change="onCoverPick" />
        </label>
        <p class="muted">支持 jpg / png / webp / gif</p>
        <el-button
          size="small"
          disabled
          title="刮削将在阶段 5 接入"
        >
          刮削…
        </el-button>
        <div class="meta muted">
          <div>字数：{{ fmtWords(book?.word_count) }}</div>
          <div>章节：{{ book?.chapter_count ?? "—" }}</div>
          <div v-if="book?.source_path" class="mono path" :title="book.source_path">
            {{ book.source_path }}
          </div>
        </div>
      </div>

      <div class="form-side page-card">
        <el-form label-position="top">
          <el-form-item label="书名" required>
            <el-input v-model="form.title" maxlength="200" />
          </el-form-item>
          <el-form-item label="作者">
            <el-input v-model="form.author" maxlength="100" placeholder="佚名" />
          </el-form-item>
          <div class="two-col">
            <el-form-item label="书源">
              <el-select v-model="form.category_source" @change="onSourceChange">
                <el-option
                  v-for="opt in sourceOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="form.category_name" filterable>
                <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="状态">
            <el-select v-model="form.status">
              <el-option label="连载" value="连载" />
              <el-option label="完结" value="完结" />
              <el-option label="未知" value="未知" />
            </el-select>
          </el-form-item>
          <el-form-item label="标签（逗号分隔）">
            <el-input v-model="form.tags" placeholder="热血, 系统流" maxlength="300" />
          </el-form-item>
          <el-form-item label="简介">
            <el-input v-model="form.intro" type="textarea" :rows="8" />
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
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
  font-size: 20px;
}

.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 800px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.cover-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cover-img {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.cover-placeholder {
  width: 100%;
  aspect-ratio: 3 / 4;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 12px;
  word-break: break-all;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
}

.upload-label:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.meta {
  line-height: 1.8;
}

.path {
  word-break: break-all;
  font-size: 11px;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
</style>
