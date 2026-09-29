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
  <div class="settings-page">
    <header class="toolbar">
      <h2>设置</h2>
    </header>

    <div class="page-card">
      <h3>外观</h3>
      <el-form label-width="60px" @submit.prevent>
        <el-form-item label="主题">
          <el-radio-group
            :model-value="theme.mode"
            @change="(v: string | number | boolean | undefined) => onThemeChange(String(v) as ThemeMode)"
          >
            <el-radio-button value="auto">跟随系统</el-radio-button>
            <el-radio-button value="light">浅色</el-radio-button>
            <el-radio-button value="dark">深色</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </div>

    <div class="page-card">
      <h3>账号</h3>
      <p class="muted">当前用户：{{ auth.username || "—" }}</p>
      <el-form label-width="96px" label-position="left" class="pw-form" @submit.prevent="savePw">
        <el-form-item label="当前密码">
          <el-input
            v-model="pwForm.old_password"
            type="password"
            show-password
            autocomplete="current-password"
            class="pw-input"
          />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="pwForm.new_password"
            type="password"
            show-password
            autocomplete="new-password"
            class="pw-input"
          />
          <span class="pw-hint">至少 6 位</span>
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input
            v-model="pwForm.new_password2"
            type="password"
            show-password
            autocomplete="new-password"
            class="pw-input"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="pwLoading" @click="savePw">保存新密码</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="page-card">
      <h3>运行环境</h3>
      <pre class="env mono">{{ envText }}</pre>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
}

h3 {
  margin: 0 0 10px;
  font-size: 14px;
}

.pw-form {
  margin-top: 8px;
}

.pw-form :deep(.el-form-item__label) {
  white-space: nowrap;
}

.pw-input {
  width: 280px;
  max-width: 100%;
}

.pw-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.env {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px;
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-all;
}

.mono {
  font-family: ui-monospace, Consolas, monospace;
}

.muted {
  color: var(--el-text-color-secondary);
}
</style>
