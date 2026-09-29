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
import AppIcon from "@/components/AppIcon.vue";

const auth = useAuthStore();
const theme = useThemeStore();
const lib = useLibraryStore();

const pwForm = ref({ old_password: "", new_password: "", new_password2: "" });
const pwLoading = ref(false);

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
</style>
