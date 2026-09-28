<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const theme = useThemeStore();

// 进入后台时应用主题（auto/light/dark）
onMounted(() => theme.init());

const navItems = [
  { path: "/", label: "书库", name: "library" },
  { path: "/import", label: "导入", name: "import" },
  { path: "/check", label: "体检", name: "check" },
  { path: "/api-docs", label: "API / 书源", name: "api-docs" },
  { path: "/settings", label: "设置", name: "settings" },
];

const activeName = computed(() => {
  if (route.name === "book-detail") return "library";
  return String(route.name || "library");
});

async function onLogout() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <el-container class="admin-wrap">
    <el-aside width="220px" class="side">
      <div class="brand">
        <span class="brand-mark">爱</span>
        <div>
          <strong>爱小说</strong>
          <div class="muted">管理后台</div>
        </div>
      </div>
      <el-menu
        :default-active="activeName"
        class="side-menu"
        router
      >
        <el-menu-item v-for="item in navItems" :key="item.name" :index="item.name">
          {{ item.label }}
        </el-menu-item>
      </el-menu>
      <div class="side-foot">
        <div class="muted">{{ auth.username || "—" }}</div>
        <el-button size="small" text @click="onLogout">退出登录</el-button>
      </div>
    </el-aside>
    <el-container>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-wrap {
  height: 100%;
}

.side {
  background: var(--app-side-bg);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  padding: 12px 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px 16px;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--el-color-primary);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.side-menu {
  border-right: none;
  flex: 1;
}

.side-foot {
  padding: 12px 16px;
  border-top: 1px solid var(--app-border);
}

.main {
  padding: 16px;
  overflow: auto;
}
</style>
