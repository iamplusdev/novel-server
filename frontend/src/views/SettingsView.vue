<script setup lang="ts">
/**
 * 设置：主题、改密（页内表单）、运行环境。
 * 退出登录仅在侧栏入口，不在本页展示。
 */
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import { useLibraryStore } from "@/stores/library";
import {
  fetchScrapeSettings,
  fetchWebDavSettings,
  saveScrapeSettings,
  saveWebDavSettings,
  testWebDav,
  type ScrapeSettingSpec,
  type ScrapeSettingsValues,
  type WebDavSettingsBody,
} from "@/api/admin";
import AppIcon from "@/components/AppIcon.vue";

const auth = useAuthStore();
const theme = useThemeStore();
const lib = useLibraryStore();

const pwForm = ref({ old_password: "", new_password: "", new_password2: "" });
const pwLoading = ref(false);

// 刮削参数（设置页可调，保存到服务端即时生效）
const scrapeSpec = ref<ScrapeSettingSpec[]>([]);
const scrapeForm = ref<ScrapeSettingsValues>({});
const scrapeSaving = ref(false);

async function loadScrape() {
  try {
    const r = await fetchScrapeSettings();
    scrapeSpec.value = r.spec;
    scrapeForm.value = { ...r.values };
  } catch {
    /* 忽略：加载失败不阻断页面 */
  }
}

async function saveScrape() {
  scrapeSaving.value = true;
  try {
    const r = await saveScrapeSettings(scrapeForm.value);
    scrapeForm.value = { ...r.values };
    ElMessage.success("刮削参数已保存");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    scrapeSaving.value = false;
  }
}

// WebDAV 进度同步（与 Legado 共用 bookProgress 目录）
const webdav = ref({
  enabled: false,
  url: "",
  username: "",
  password: "",
  dir: "legado",
  timeout: 6,
  verify_tls: true,
  clear_password: false,
});
const webdavHasPassword = ref(false);
const webdavSaving = ref(false);
const webdavTesting = ref(false);

async function loadWebdav() {
  try {
    const r = await fetchWebDavSettings();
    webdav.value = {
      enabled: r.enabled,
      url: r.url,
      username: r.username,
      password: "",
      dir: r.dir,
      timeout: r.timeout,
      verify_tls: r.verify_tls,
      clear_password: false,
    };
    webdavHasPassword.value = r.has_password;
  } catch {
    /* 忽略：加载失败不阻断页面 */
  }
}

async function saveWebdav() {
  webdavSaving.value = true;
  try {
    const body: WebDavSettingsBody = {
      enabled: webdav.value.enabled,
      url: webdav.value.url,
      username: webdav.value.username,
      dir: webdav.value.dir,
      timeout: webdav.value.timeout,
      verify_tls: webdav.value.verify_tls,
      clear_password: webdav.value.clear_password,
    };
    if (webdav.value.password) body.password = webdav.value.password;
    const r = await saveWebDavSettings(body);
    webdavHasPassword.value = r.has_password;
    webdav.value.password = "";
    webdav.value.clear_password = false;
    ElMessage.success("WebDAV 配置已保存");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    webdavSaving.value = false;
  }
}

async function runWebdavTest() {
  webdavTesting.value = true;
  try {
    const r = await testWebDav();
    if (r.ok) ElMessage.success(r.message || "连接成功");
    else ElMessage.error(r.error || "连接失败");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "连接失败");
  } finally {
    webdavTesting.value = false;
  }
}

const envText = computed(() => {
  const s = lib.stats;
  if (!s) return "加载中…";
  return [
    "对外地址  " + (s.public_base_url || location.origin),
    "书籍目录  " + (s.novels_dir || "—"),
    "数据库    " + (s.database_path || "—"),
    "封面目录  " + (s.covers_dir || "—"),
  ].join("\n");
});

function onThemeChange(mode: ThemeMode) {
  theme.setMode(mode);
  ElMessage.success("主题已切换");
}

async function savePw() {
  const { old_password, new_password, new_password2 } = pwForm.value;
  if (!old_password) {
    ElMessage.warning("请输入当前密码");
    return;
  }
  if (!new_password || new_password.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  if (new_password !== new_password2) {
    ElMessage.warning("两次新密码不一致");
    return;
  }
  pwLoading.value = true;
  try {
    await auth.changePassword(old_password, new_password);
    pwForm.value = { old_password: "", new_password: "", new_password2: "" };
    ElMessage.success("密码已修改");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "修改失败");
  } finally {
    pwLoading.value = false;
  }
}

onMounted(async () => {
  theme.init();
  void loadScrape();
  void loadWebdav();
  try {
    await lib.loadStats();
  } catch {
    /* ignore */
  }
});
</script>

<template>
  <div class="page settings-page">
    <header class="page-header">
      <h1 class="page-title">设置</h1>
    </header>

    <section class="page-card">
      <div class="section-head">
        <AppIcon name="palette" :size="16" />
        <h2 class="section-title">外观</h2>
      </div>
      <div class="theme-row" role="radiogroup" aria-label="主题">
        <button
          v-for="opt in [
            { value: 'auto', label: '跟随系统' },
            { value: 'light', label: '浅色' },
            { value: 'dark', label: '深色' },
          ]"
          :key="opt.value"
          type="button"
          class="theme-opt"
          :class="{ 'is-active': theme.mode === opt.value }"
          @click="onThemeChange(opt.value as ThemeMode)"
        >
          {{ opt.label }}
        </button>
      </div>
    </section>

    <section class="page-card">
      <div class="section-head">
        <AppIcon name="settings" :size="16" />
        <h2 class="section-title">账号</h2>
      </div>
      <p class="muted">当前用户：{{ auth.username || "—" }}</p>
      <form class="pw-form" @submit.prevent="savePw">
        <div class="field">
          <label class="field-label">当前密码</label>
          <input
            v-model="pwForm.old_password"
            type="password"
            class="field-input"
            autocomplete="current-password"
          />
        </div>
        <div class="field">
          <label class="field-label">新密码</label>
          <input
            v-model="pwForm.new_password"
            type="password"
            class="field-input"
            autocomplete="new-password"
          />
          <span class="pw-hint">至少 6 位</span>
        </div>
        <div class="field">
          <label class="field-label">确认密码</label>
          <input
            v-model="pwForm.new_password2"
            type="password"
            class="field-input"
            autocomplete="new-password"
          />
        </div>
        <button type="submit" class="primary-btn" :disabled="pwLoading">
          {{ pwLoading ? "保存中…" : "保存新密码" }}
        </button>
      </form>
    </section>

    <section class="page-card">
      <div class="section-head">
        <AppIcon name="settings" :size="16" />
        <h2 class="section-title">刮削参数</h2>
      </div>
      <p class="muted">
        批量刮削节奏与防风控限速/重试；保存后<strong>即时生效</strong>（未保存则用环境变量默认值）。
      </p>
      <div class="scrape-form">
        <label v-for="s in scrapeSpec" :key="s.key" class="scrape-field">
          <span class="scrape-label">
            {{ s.label }}<em v-if="s.unit">（{{ s.unit }}）</em>
          </span>
          <el-switch
            v-if="s.type === 'bool'"
            :model-value="scrapeForm[s.key] === true"
            @update:model-value="
              (v: string | number | boolean) => (scrapeForm[s.key] = Boolean(v))
            "
          />
          <input
            v-else
            v-model.number="scrapeForm[s.key]"
            type="number"
            class="field-input"
            :min="s.min"
            :max="s.max"
            :step="s.type === 'int' ? 1 : 0.1"
          />
          <span v-if="s.hint" class="scrape-hint muted-xs">{{ s.hint }}</span>
        </label>
      </div>
      <button
        type="button"
        class="primary-btn"
        :disabled="scrapeSaving || !scrapeSpec.length"
        @click="saveScrape"
      >
        {{ scrapeSaving ? "保存中…" : "保存刮削参数" }}
      </button>
    </section>

    <section class="page-card">
      <div class="section-head">
        <AppIcon name="api" :size="16" />
        <h2 class="section-title">WebDAV 进度同步</h2>
      </div>
      <p class="muted">
        与 Legado 共用同一个 WebDAV 的 <code>bookProgress</code> 目录：打开阅读页拉取最新进度，关闭页面时推送。
        需在 Legado 中开启「同步阅读进度」。
      </p>
      <div class="scrape-form">
        <label class="scrape-field">
          <span class="scrape-label">启用同步</span>
          <el-switch v-model="webdav.enabled" />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">WebDAV 地址</span>
          <input
            v-model="webdav.url"
            class="field-input"
            placeholder="https://dav.example.com/dav/"
          />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">账号</span>
          <input v-model="webdav.username" class="field-input" autocomplete="username" />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">密码</span>
          <input
            v-model="webdav.password"
            type="password"
            class="field-input"
            autocomplete="current-password"
            :placeholder="webdavHasPassword ? '已保存，留空不修改' : ''"
          />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">目录</span>
          <input v-model="webdav.dir" class="field-input" placeholder="legado" />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">超时（秒）</span>
          <input
            v-model.number="webdav.timeout"
            type="number"
            min="2"
            max="20"
            class="field-input"
          />
        </label>
        <label class="scrape-field">
          <span class="scrape-label">校验证书</span>
          <el-switch v-model="webdav.verify_tls" />
          <span class="scrape-hint muted-xs">自签名 NAS 证书可关闭</span>
        </label>
      </div>
      <label v-if="webdavHasPassword" class="muted-xs webdav-clear">
        <input v-model="webdav.clear_password" type="checkbox" />
        清除已保存的密码
      </label>
      <div class="btn-row">
        <button type="button" class="primary-btn" :disabled="webdavSaving" @click="saveWebdav">
          {{ webdavSaving ? "保存中…" : "保存 WebDAV 配置" }}
        </button>
        <button type="button" class="ghost-btn" :disabled="webdavTesting" @click="runWebdavTest">
          {{ webdavTesting ? "测试中…" : "测试已保存的配置" }}
        </button>
      </div>
      <p class="scrape-hint muted-xs">
        文件名由「书名_作者」决定，需与 Legado 中的书名、作者完全一致。
      </p>
    </section>

    <section class="page-card">
      <div class="section-head">
        <AppIcon name="api" :size="16" />
        <h2 class="section-title">运行环境</h2>
      </div>
      <pre class="log-panel env">{{ envText }}</pre>
    </section>
  </div>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--space-3);
  color: var(--color-text-2);
}

.section-head .section-title {
  margin: 0;
  color: var(--color-text);
}

.theme-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.theme-opt {
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
}

.theme-opt:hover {
  border-color: var(--color-border-strong);
  color: var(--color-text);
}

.theme-opt.is-active {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  color: var(--color-accent);
  font-weight: 600;
}

.pw-form {
  margin-top: var(--space-3);
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: var(--text-xs);
  color: var(--color-text-2);
  font-weight: 500;
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

.pw-hint {
  font-size: var(--text-xs);
  color: var(--color-text-3);
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
  align-self: flex-start;
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.env {
  max-height: none;
}

.btn-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: var(--space-2);
}

.ghost-btn {
  height: 36px;
  padding: 0 16px;
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

.ghost-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.webdav-clear {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

/* 刮削参数表单：自适应多列；label 在上、输入框撑满单元格 → 各行对齐 */
.scrape-form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-3) var(--space-4);
  margin: var(--space-3) 0 var(--space-4);
}

.scrape-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.scrape-label {
  font-size: var(--text-sm);
  color: var(--color-text-2);
  font-weight: 500;
}

.scrape-label em {
  font-style: normal;
  color: var(--color-text-3);
}

/* 输入框占满单元格宽度，跨行/跨列起点一致对齐 */
.scrape-field .field-input {
  width: 100%;
}

.scrape-field :deep(.el-switch) {
  align-self: flex-start;
}

.scrape-hint {
  margin-top: 2px;
}
</style>
