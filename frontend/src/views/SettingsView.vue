<script setup lang="ts">
/**
 * 设置：主题、账号（改密/退出）、运行环境。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import { useLibraryStore } from "@/stores/library";

const router = useRouter();
const auth = useAuthStore();
const theme = useThemeStore();
const lib = useLibraryStore();

const pwDialog = ref(false);
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

async function openPw() {
  pwForm.value = { old_password: "", new_password: "", new_password2: "" };
  pwDialog.value = true;
}

async function savePw() {
  const { old_password, new_password, new_password2 } = pwForm.value;
  if (!old_password) return ElMessage.warning("请输入当前密码");
  if (!new_password || new_password.length < 6) return ElMessage.warning("新密码至少 6 位");
  if (new_password !== new_password2) return ElMessage.warning("两次新密码不一致");
  pwLoading.value = true;
  try {
    await auth.changePassword(old_password, new_password);
    pwDialog.value = false;
    ElMessage.success("密码已修改");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "修改失败");
  } finally {
    pwLoading.value = false;
  }
}

async function logout() {
  try {
    await ElMessageBox.confirm("确认退出登录？", "退出登录", {
      type: "warning",
      confirmButtonText: "退出",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  await auth.logout();
  router.push({ name: "login" });
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
      <div class="actions">
        <el-button type="primary" @click="openPw">修改密码</el-button>
        <el-button @click="logout">退出登录</el-button>
      </div>
    </div>

    <div class="page-card">
      <h3>运行环境</h3>
      <pre class="env mono">{{ envText }}</pre>
    </div>

    <el-dialog v-model="pwDialog" title="修改密码" width="420px">
      <el-form label-position="top" @submit.prevent="savePw">
        <el-form-item label="当前密码">
          <el-input
            v-model="pwForm.old_password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）">
          <el-input
            v-model="pwForm.new_password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input
            v-model="pwForm.new_password2"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <p class="muted">修改成功后会自动重新登录。</p>
      </el-form>
      <template #footer>
        <el-button @click="pwDialog = false">取消</el-button>
        <el-button type="primary" :loading="pwLoading" @click="savePw">保存</el-button>
      </template>
    </el-dialog>
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

.actions {
  display: flex;
  gap: 8px;
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
</style>
