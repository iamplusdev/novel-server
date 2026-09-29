<script setup lang="ts">
/**
 * 登录 / 首次初始化 / 忘记密码 / 恢复码 —— 对齐旧版 auth 流程。
 * 面板互斥：login | setup | forgot | recovery
 */
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";

type Pane = "login" | "setup" | "forgot" | "recovery";

const router = useRouter();
const auth = useAuthStore();

const pane = ref<Pane>("login");
const loading = ref(false);
const errorMsg = ref("");
const recoveryCode = ref("");

const loginForm = reactive({ username: "", password: "" });
const setupForm = reactive({ username: "", password: "", password2: "" });
const forgotForm = reactive({ recovery_code: "", username: "", new_password: "" });

const subtitle = computed(() => {
  if (auth.setupRequired || pane.value === "setup") return "首次使用 · 请创建管理账号";
  if (pane.value === "forgot") return "使用恢复码重设账号";
  if (pane.value === "recovery") return "请立即保存恢复码";
  return "管理后台 · 账号登录";
});

function show(p: Pane) {
  pane.value = p;
  errorMsg.value = "";
}

function fail(msg: string) {
  errorMsg.value = msg || "操作失败";
}

onMounted(async () => {
  try {
    const st = await auth.fetchStatus();
    if (st.setup_required) {
      show("setup");
      return;
    }
    // 已有会话则直接进入后台
    if (await auth.tryRestore()) {
      router.replace({ name: "library" });
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : "无法连接服务器");
  }
});

async function doLogin() {
  const username = loginForm.username.trim();
  const password = loginForm.password;
  if (!username || !password) return fail("请输入用户名和密码");
  loading.value = true;
  errorMsg.value = "";
  try {
    loginForm.password = "";
    await auth.login(username, password);
    ElMessage.success("登录成功");
    router.replace({ name: "library" });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "登录失败";
    if (msg.includes("尚未设置") || msg.includes("创建")) {
      show("setup");
      fail("首次使用请先创建账号（下方表单）");
    } else {
      fail(msg);
    }
  } finally {
    loading.value = false;
  }
}

async function doSetup() {
  const username = setupForm.username.trim();
  const password = setupForm.password;
  if (!username) return fail("请填写用户名");
  if (!password || password.length < 6) return fail("密码至少 6 位");
  if (password !== setupForm.password2) return fail("两次密码不一致");
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await auth.setup(username, password);
    setupForm.password = "";
    setupForm.password2 = "";
    if (res.recovery_code) {
      recoveryCode.value = res.recovery_code;
      show("recovery");
      ElMessage.success("账号已创建，请保存恢复码");
    } else {
      router.replace({ name: "library" });
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : "创建失败");
  } finally {
    loading.value = false;
  }
}

async function doForgot() {
  const code = forgotForm.recovery_code.trim();
  const password = forgotForm.new_password;
  if (!code) return fail("请填写恢复码");
  if (!password || password.length < 6) return fail("新密码至少 6 位");
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await auth.forgot({
      recovery_code: code,
      username: forgotForm.username.trim() || null,
      new_password: password,
    });
    forgotForm.new_password = "";
    if (res.recovery_code) {
      recoveryCode.value = res.recovery_code;
      show("recovery");
      ElMessage.success("已重设账号，恢复码已更换");
    } else {
      router.replace({ name: "library" });
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : "重设失败");
  } finally {
    loading.value = false;
  }
}

async function copyRecovery() {
  try {
    await navigator.clipboard.writeText(recoveryCode.value);
    ElMessage.success("已复制恢复码");
  } catch {
    ElMessage.warning("复制失败，请手动选择文本复制");
  }
}

function enterApp() {
  router.replace({ name: "library" });
}
</script>

<template>
  <div class="login-page">
    <div class="login-bg" aria-hidden="true" />
    <div class="login-veil" aria-hidden="true" />
    <el-card class="login-card" shadow="never">
      <div class="brand">
        <span class="brand-mark">爱</span>
        <div>
          <h1>爱小说</h1>
          <p class="subtitle">{{ subtitle }}</p>
        </div>
      </div>

      <!-- 登录 -->
      <el-form v-if="pane === 'login'" label-position="top" @submit.prevent="doLogin">
        <el-form-item label="用户名">
          <el-input
            v-model="loginForm.username"
            autocomplete="username"
            placeholder="用户名"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="loginForm.password"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="密码"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button type="primary" class="block-btn" :loading="loading" @click="doLogin">
          登录
        </el-button>
        <div class="auth-links">
          <el-button link type="primary" @click="show('forgot')">忘记密码</el-button>
        </div>
      </el-form>

      <!-- 首次初始化 -->
      <el-form v-else-if="pane === 'setup'" label-position="top" @submit.prevent="doSetup">
        <p class="hint">首次使用：输入的用户名和密码将设为管理账号，请妥善保管。</p>
        <el-form-item label="用户名">
          <el-input v-model="setupForm.username" autocomplete="username" placeholder="例如 admin" />
        </el-form-item>
        <el-form-item label="密码（至少 6 位）">
          <el-input
            v-model="setupForm.password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input
            v-model="setupForm.password2"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-button type="primary" class="block-btn" :loading="loading" @click="doSetup">
          创建账号并进入
        </el-button>
      </el-form>

      <!-- 忘记密码 -->
      <el-form v-else-if="pane === 'forgot'" label-position="top" @submit.prevent="doForgot">
        <p class="hint">
          使用初始化时保存的恢复码重设账号。若已丢失，请在服务器执行
          <code>python reset_auth.py</code>。
        </p>
        <el-form-item label="恢复码">
          <el-input
            v-model="forgotForm.recovery_code"
            placeholder="XXXX-XXXX-XXXX-XXXX"
            class="mono"
          />
        </el-form-item>
        <el-form-item label="新用户名（可选，留空不变）">
          <el-input v-model="forgotForm.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）">
          <el-input
            v-model="forgotForm.new_password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-button type="primary" class="block-btn" :loading="loading" @click="doForgot">
          重设并登录
        </el-button>
        <div class="auth-links">
          <el-button link type="primary" @click="show('login')">返回登录</el-button>
        </div>
      </el-form>

      <!-- 恢复码展示 -->
      <div v-else class="recovery-pane">
        <el-alert
          type="warning"
          :closable="false"
          title="请立即保存恢复码，离开本页面后无法再次查看！"
          class="mb12"
        />
        <div class="recovery-box mono">{{ recoveryCode }}</div>
        <div class="row-btns">
          <el-button @click="copyRecovery">复制恢复码</el-button>
          <el-button type="primary" @click="enterApp">我已保存，进入后台</el-button>
        </div>
      </div>

      <el-alert
        v-if="errorMsg"
        type="error"
        :closable="false"
        :title="errorMsg"
        class="mb12"
      />

      <p v-if="pane !== 'recovery'" class="hint">
        也可在服务器执行 <code>python reset_auth.py</code> 紧急重置账号。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100%;
  display: flex;
  align-items: center;
  /* 垂直居中 + 水平靠右 */
  justify-content: flex-end;
  padding: 24px 8vw 24px 24px;
  overflow: hidden;
}

/* 全屏背景图 */
.login-bg {
  position: absolute;
  inset: 0;
  background:
    url("/bg_login.jpg") center / cover no-repeat;
  transform: scale(1.02);
}

/* 整页不遮罩，仅表单卡片用 #5d6369 透明底 */
.login-veil {
  display: none;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 400px;
  max-width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  /* #5d6369 略实，减少背景透出干扰 */
  background: rgba(93, 99, 105, 0.82);
  backdrop-filter: blur(18px) saturate(1.1);
  -webkit-backdrop-filter: blur(18px) saturate(1.1);
  box-shadow:
    0 20px 50px rgba(0, 0, 0, 0.32),
    0 2px 8px rgba(0, 0, 0, 0.14);
  padding: 8px 4px 4px;
  color: #f2f4f6;
}

.login-card :deep(.el-card__body) {
  padding: 22px 26px 20px;
}

/* 标题与表单标签统一浅色（强制覆盖 EP 默认灰） */
.login-card .brand h1 {
  color: #f7f8fa;
}

.login-card :deep(.el-form .el-form-item__label),
.login-card :deep(.el-form-item__label),
.login-card :deep(label.el-form-item__label) {
  color: #ffffff !important;
  opacity: 0.95;
  font-weight: 600;
  font-size: 13px;
  line-height: 1.4;
}

.login-card .brand .subtitle,
.login-card .hint {
  color: rgba(242, 244, 246, 0.68);
}

/* 输入框 */
.login-card :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.login-card :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.32) inset;
}

.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(64, 158, 255, 0.9) inset,
    0 0 0 3px rgba(64, 158, 255, 0.25);
}

.login-card :deep(.el-input__inner) {
  color: #fff;
}

.login-card :deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.5);
}

/* 链接 */
.login-card :deep(.el-button.is-link) {
  color: #79bbff;
  font-weight: 500;
}

.login-card :deep(.el-button.is-link:hover) {
  color: #a0cfff;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 4px 0 18px;
}

.brand h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
}

.brand .subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.brand-mark {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 20px;
  box-shadow: 0 6px 16px rgba(64, 158, 255, 0.35);
}

.login-card :deep(.el-form-item) {
  margin-bottom: 16px;
}

.login-card :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.login-card :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--el-border-color) inset;
}

.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px var(--el-color-primary) inset,
    0 0 0 3px rgba(64, 158, 255, 0.18);
}

.block-btn {
  width: 100%;
  height: 40px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  margin-top: 4px;
  box-shadow: 0 6px 16px rgba(64, 158, 255, 0.28);
}

.auth-links {
  margin-top: 10px;
  text-align: center;
}

.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  margin: 10px 0 0;
}

.recovery-box {
  background: rgba(255, 255, 255, 0.12);
  border: 1.5px dashed rgba(255, 255, 255, 0.45);
  border-radius: 10px;
  padding: 18px;
  text-align: center;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
  word-break: break-all;
  margin: 8px 0 14px;
  color: #fff;
}

.row-btns {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.mb12 {
  margin-bottom: 12px;
}

.login-card code {
  font-family: ui-monospace, Consolas, monospace;
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.88);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

@media (max-width: 480px) {
  .login-page {
    padding: 16px;
    justify-content: center;
    align-items: flex-start;
    padding-top: 48px;
  }

  .login-card :deep(.el-card__body) {
    padding: 18px 16px 16px;
  }

  .brand h1 {
    font-size: 20px;
  }
}
</style>
