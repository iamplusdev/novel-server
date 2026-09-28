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
    <el-card class="login-card">
      <div class="brand">
        <span class="brand-mark">爱</span>
        <div>
          <h1>爱小说</h1>
          <p class="muted">{{ subtitle }}</p>
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
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  width: 400px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.brand h1 {
  margin: 0;
  font-size: 20px;
}

.brand p {
  margin: 2px 0 0;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--el-color-primary);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 18px;
}

.block-btn {
  width: 100%;
}

.auth-links {
  margin-top: 8px;
  text-align: center;
}

.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.recovery-box {
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  font-size: 18px;
  letter-spacing: 1px;
  word-break: break-all;
  margin-bottom: 12px;
}

.row-btns {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.mb12 {
  margin-bottom: 12px;
}

code {
  font-family: ui-monospace, Consolas, monospace;
  background: var(--el-fill-color-light);
  padding: 1px 4px;
  border-radius: 4px;
}
</style>
