<script setup lang="ts">
/**
 * 公开 API / Legado 书源说明与下载。
 */
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { http } from "@/api/client";
import { useLibraryStore } from "@/stores/library";

const lib = useLibraryStore();
const apiBase = ref(location.origin);
const sourceJson = ref("");

const publicApis = [
  "GET /api/categories",
  "GET /api/books?category=&q=&page=",
  "GET /api/books/{id}",
  "GET /api/books/{id}/chapters",
  "GET /api/books/{id}/chapters/{chapter_id}",
  "GET /api/search?q=",
];

const legadoApis = [
  "GET /api/legado/explore/{分类}?page=",
  "GET /api/legado/search?q=&page=",
  "GET /api/legado/book/{id}",
  "GET /api/legado/toc/{id}",
  "GET /api/legado/content/{book_id}/{chapter_id}",
];

async function loadSource() {
  try {
    let json: unknown = await http.get<unknown>("/api/legado/book-source");
    const base = lib.stats?.public_base_url || location.origin;
    const items = Array.isArray(json) ? json : [json];
    items.forEach((item) => {
      if (item && typeof item === "object") {
        (item as Record<string, unknown>).bookSourceUrl = base;
      }
    });
    sourceJson.value = JSON.stringify(items, null, 2);
  } catch {
    try {
      const res = await fetch("/legado_book_source.json");
      if (!res.ok) throw new Error("书源文件不存在");
      let json: unknown = await res.json();
      const base = lib.stats?.public_base_url || location.origin;
      const items = Array.isArray(json) ? json : [json];
      items.forEach((item) => {
        if (item && typeof item === "object") {
          (item as Record<string, unknown>).bookSourceUrl = base;
        }
      });
      sourceJson.value = JSON.stringify(Array.isArray(json) ? items : items, null, 2);
    } catch (e) {
      sourceJson.value = "无法加载书源: " + (e instanceof Error ? e.message : String(e));
    }
  }
}

async function copySource() {
  try {
    await navigator.clipboard.writeText(sourceJson.value);
    ElMessage.success("书源 JSON 已复制");
  } catch {
    ElMessage.warning("复制失败，请手动选择文本复制");
  }
}

onMounted(async () => {
  try {
    await lib.loadStats();
    if (lib.stats?.public_base_url) apiBase.value = lib.stats.public_base_url;
  } catch {
    /* ignore */
  }
  await loadSource();
});
</script>

<template>
  <div class="api-page">
    <header class="toolbar">
      <h2>API / Legado 书源</h2>
    </header>

    <div class="page-card">
      <h3>服务地址</h3>
      <p class="mono">{{ apiBase }}</p>
      <p class="muted">
        请在服务端设置 <code>PUBLIC_BASE_URL</code> 为手机可访问的局域网或穿透地址，书源与封面绝对地址都依赖它。
      </p>
    </div>

    <div class="page-card">
      <h3>公开 JSON API</h3>
      <ul class="mono api-list">
        <li v-for="p in publicApis" :key="p">{{ p }}</li>
      </ul>
    </div>

    <div class="page-card">
      <h3>Legado 书源 API（完整 URL）</h3>
      <ul class="mono api-list">
        <li v-for="p in legadoApis" :key="p">{{ p }}</li>
      </ul>
    </div>

    <div class="page-card">
      <h3>书源 JSON</h3>
      <p class="muted">
        下载后在开源阅读 Legado → 我的 → 书源管理 → 本地导入。若开启了全局鉴权，可在 header 中加入 Bearer Token。
      </p>
      <div class="actions">
        <a class="el-button el-button--primary" href="/legado_book_source.json" download>
          下载书源 JSON
        </a>
        <el-button @click="copySource">复制书源 JSON</el-button>
      </div>
      <pre class="log">{{ sourceJson }}</pre>
    </div>
  </div>
</template>

<style scoped>
.api-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
}

h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.api-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 8px;
  margin: 10px 0;
}

.log {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

code {
  font-family: ui-monospace, Consolas, monospace;
  background: var(--el-fill-color-light);
  padding: 1px 4px;
  border-radius: 4px;
}

.mono {
  font-family: ui-monospace, Consolas, monospace;
}
</style>
