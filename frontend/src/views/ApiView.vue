<script setup lang="ts">
/**
 * API 说明 / Legado 书源（Tab 切换）。
 * 「复制书源」= 复制书源 JSON 的下载 URL。
 */
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { http } from "@/api/client";
import { useLibraryStore } from "@/stores/library";

const lib = useLibraryStore();
const activeTab = ref("api");
const apiBase = ref(location.origin);

const sourceJsonUrl = computed(
  () => `${apiBase.value.replace(/\/$/, "")}/legado_book_source.json`,
);

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

async function copySourceUrl() {
  try {
    await navigator.clipboard.writeText(sourceJsonUrl.value);
    ElMessage.success("书源 URL 已复制");
  } catch {
    ElMessage.warning("复制失败，请手动复制：" + sourceJsonUrl.value);
  }
}

onMounted(async () => {
  try {
    await lib.loadStats();
    if (lib.stats?.public_base_url) apiBase.value = lib.stats.public_base_url;
  } catch {
    /* ignore */
  }
  // 预加载校验书源接口可达
  try {
    await http.get("/api/legado/book-source");
  } catch {
    /* 忽略：页面不依赖此结果 */
  }
});
</script>

<template>
  <div class="api-page">
    <header class="toolbar">
      <h2>API</h2>
    </header>

    <el-tabs v-model="activeTab" class="api-tabs">
      <el-tab-pane label="API" name="api">
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
      </el-tab-pane>

      <el-tab-pane label="书源" name="source">
        <div class="page-card">
          <h3>书源 JSON</h3>
          <p class="muted">
            下载后在开源阅读 Legado → 我的 → 书源管理 → 本地导入。若开启了全局鉴权，可在 header 中加入 Bearer Token。
          </p>
          <p class="mono url-line">{{ sourceJsonUrl }}</p>
          <div class="actions">
            <a class="el-button el-button--primary" :href="sourceJsonUrl" download>下载书源</a>
            <el-button @click="copySourceUrl">复制书源</el-button>
          </div>
          <p class="muted">「复制书源」复制的是书源 JSON 的下载 URL。</p>
        </div>
      </el-tab-pane>
    </el-tabs>
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

.api-tabs {
  background: var(--el-bg-color);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 8px 16px 16px;
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

.url-line {
  font-size: 12px;
  word-break: break-all;
  color: var(--el-text-color-secondary);
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
