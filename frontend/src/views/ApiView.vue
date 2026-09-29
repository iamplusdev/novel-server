<script setup lang="ts">
/**
 * API 说明 / Legado 书源（Tab 切换）。
 * 「复制书源」= 复制书源 JSON 的下载 URL。
 */
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { http } from "@/api/client";
import { useLibraryStore } from "@/stores/library";
import AppIcon from "@/components/AppIcon.vue";

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

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制");
  } catch {
    ElMessage.warning("复制失败");
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
  <div class="page api-page">
    <header class="page-header">
      <h1 class="page-title">API / 书源</h1>
    </header>

    <section class="page-card tabs-card">
      <div class="tab-nav" role="tablist">
        <button
          type="button"
          class="tab-btn"
          :class="{ 'is-active': activeTab === 'api' }"
          @click="activeTab = 'api'"
        >
          API
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ 'is-active': activeTab === 'source' }"
          @click="activeTab = 'source'"
        >
          书源
        </button>
      </div>

      <div v-if="activeTab === 'api'" class="tab-panel">
        <h2 class="section-title">服务地址</h2>
        <div class="url-block">
          <code class="url mono">{{ apiBase }}</code>
          <button type="button" class="ghost-btn sm" @click="copyText(apiBase)">
            <AppIcon name="copy" :size="14" />
            复制
          </button>
        </div>
        <p class="muted">
          请在服务端设置 <code>PUBLIC_BASE_URL</code> 为手机可访问的局域网或穿透地址，书源与封面绝对地址都依赖它。
        </p>

        <h2 class="section-title">公开 JSON API</h2>
        <ul class="api-list mono">
          <li v-for="p in publicApis" :key="p">
            <code>{{ p }}</code>
            <button type="button" class="link-btn" @click="copyText(p)">复制</button>
          </li>
        </ul>

        <h2 class="section-title">Legado 书源 API（完整 URL）</h2>
        <ul class="api-list mono">
          <li v-for="p in legadoApis" :key="p">
            <code>{{ p }}</code>
            <button type="button" class="link-btn" @click="copyText(p)">复制</button>
          </li>
        </ul>
      </div>

      <div v-else class="tab-panel">
        <h2 class="section-title">书源 JSON</h2>
        <p class="muted">
          下载后在开源阅读 Legado → 我的 → 书源管理 → 本地导入。若开启了全局鉴权，可在 header 中加入 Bearer Token。
        </p>
        <div class="url-block">
          <code class="url mono">{{ sourceJsonUrl }}</code>
        </div>
        <div class="actions">
          <a class="primary-link" :href="sourceJsonUrl" download>
            <AppIcon name="import" :size="14" />
            下载书源
          </a>
          <button type="button" class="ghost-btn" @click="copySourceUrl">
            <AppIcon name="copy" :size="14" />
            复制书源
          </button>
        </div>
        <p class="muted-xs">「复制书源」复制的是书源 JSON 的下载 URL。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
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

.section-title {
  margin: var(--space-4) 0 var(--space-2);
}

.section-title:first-child {
  margin-top: 0;
}

.url-block {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}

.url {
  flex: 1;
  min-width: 0;
  font-size: var(--text-xs);
  word-break: break-all;
  color: var(--color-text);
}

.api-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.api-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.api-list code {
  font-size: var(--text-xs);
  word-break: break-all;
  background: none;
  padding: 0;
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
  height: 28px;
  padding: 0 8px;
  font-size: var(--text-xs);
}

.ghost-btn:hover {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.primary-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
}

.primary-link:hover {
  background: var(--color-accent-hover);
  color: #fff;
}

.actions {
  display: flex;
  gap: 8px;
  margin: 12px 0;
  flex-wrap: wrap;
}

.link-btn {
  border: none;
  background: none;
  color: var(--color-accent);
  font-size: var(--text-xs);
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
}

.mono {
  font-family: var(--font-mono);
}

code {
  font-family: var(--font-mono);
  background: var(--color-surface-3);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
