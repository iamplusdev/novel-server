<script setup lang="ts">
/**
 * 后台布局：品牌侧栏 + 主内容区。
 * 桌面固定侧栏；≤900px 改为顶栏 + 抽屉导航。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import AppIcon from "@/components/AppIcon.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const theme = useThemeStore();

const drawerOpen = ref(false);
const isNarrow = ref(false);

// 进入后台时应用主题（auto/light/dark）
onMounted(() => {
  theme.init();
  syncNarrow();
  window.addEventListener("resize", syncNarrow);
});

function syncNarrow() {
  isNarrow.value = window.innerWidth <= 900;
  if (!isNarrow.value) drawerOpen.value = false;
}

const navItems = [
  { path: "/", label: "书库", name: "library", icon: "library" },
  { path: "/import", label: "导入", name: "import", icon: "import" },
  { path: "/check", label: "体检", name: "check", icon: "check" },
  { path: "/api-docs", label: "API", name: "api-docs", icon: "api" },
  { path: "/settings", label: "设置", name: "settings", icon: "settings" },
];

const activeName = computed(() => {
  if (route.name === "book-detail" || route.name === "book-read") return "library";
  return String(route.name || "library");
});

const themeIcon = computed(() => {
  if (theme.mode === "light") return "sun";
  if (theme.mode === "dark") return "moon";
  return "palette";
});

/** 用 named 路由跳转：避免 el-menu router 模式把 name 当 path，在详情页点不动 */
function onMenuSelect(name: string) {
  if (!name || name === String(route.name)) {
    drawerOpen.value = false;
    return;
  }
  drawerOpen.value = false;
  void router.push({ name });
}

async function onLogout() {
  await auth.logout();
  router.push({ name: "login" });
}

function cycleTheme() {
  const order: ThemeMode[] = ["auto", "light", "dark"];
  const idx = order.indexOf(theme.mode);
  const next = order[(idx + 1) % order.length]!;
  theme.setMode(next);
}

const themeLabel = computed(() => {
  if (theme.mode === "light") return "浅色";
  if (theme.mode === "dark") return "深色";
  return "跟随系统";
});
</script>

<template>
  <el-container class="admin-wrap">
    <!-- 桌面侧栏 -->
    <el-aside v-if="!isNarrow" width="240px" class="side">
      <div class="brand">
        <span class="brand-mark">爱</span>
        <div class="brand-text">
          <strong>爱小说</strong>
          <div class="muted-xs">管理后台</div>
        </div>
      </div>

      <nav class="side-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.name"
          type="button"
          class="nav-item"
          :class="{ 'is-active': activeName === item.name }"
          @click="onMenuSelect(item.name)"
        >
          <AppIcon :name="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="side-foot">
        <button type="button" class="theme-btn" :title="`主题：${themeLabel}`" @click="cycleTheme">
          <AppIcon :name="themeIcon" :size="16" />
          <span>{{ themeLabel }}</span>
        </button>
        <div class="user-chip">
          <span class="avatar">{{ (auth.username || "·").slice(0, 1) }}</span>
          <div class="user-meta">
            <div class="user-name">{{ auth.username || "未登录" }}</div>
            <div class="user-sub">管理员</div>
          </div>
          <button type="button" class="icon-btn" title="退出登录" @click="onLogout">
            <AppIcon name="logout" :size="16" />
          </button>
        </div>
      </div>
    </el-aside>

    <el-container class="main-col">
      <!-- 窄屏顶栏 -->
      <header v-if="isNarrow" class="topbar">
        <button type="button" class="icon-btn" aria-label="打开导航" @click="drawerOpen = true">
          <AppIcon name="menu" :size="20" />
        </button>
        <div class="topbar-brand">
          <span class="brand-mark sm">爱</span>
          <strong>爱小说</strong>
        </div>
        <button type="button" class="icon-btn" :title="`主题：${themeLabel}`" @click="cycleTheme">
          <AppIcon :name="themeIcon" :size="18" />
        </button>
      </header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 窄屏抽屉导航 -->
    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      size="280px"
      :with-header="false"
      class="nav-drawer"
    >
      <div class="drawer-inner">
        <div class="brand">
          <span class="brand-mark">爱</span>
          <div class="brand-text">
            <strong>爱小说</strong>
            <div class="muted-xs">管理后台</div>
          </div>
        </div>
        <nav class="side-nav" aria-label="主导航">
          <button
            v-for="item in navItems"
            :key="item.name"
            type="button"
            class="nav-item"
            :class="{ 'is-active': activeName === item.name }"
            @click="onMenuSelect(item.name)"
          >
            <AppIcon :name="item.icon" :size="18" />
            <span>{{ item.label }}</span>
          </button>
        </nav>
        <div class="side-foot">
          <div class="user-chip">
            <span class="avatar">{{ (auth.username || "·").slice(0, 1) }}</span>
            <div class="user-meta">
              <div class="user-name">{{ auth.username || "未登录" }}</div>
              <div class="user-sub">管理员</div>
            </div>
            <button type="button" class="icon-btn" title="退出登录" @click="onLogout">
              <AppIcon name="logout" :size="16" />
            </button>
          </div>
        </div>
      </div>
    </el-drawer>
  </el-container>
</template>

<style scoped>
.admin-wrap {
  height: 100%;
  background: var(--color-bg);
}

.side {
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  padding: var(--space-3) 0;
  width: 240px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: var(--space-2) var(--space-4) var(--space-4);
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.brand-mark.sm {
  width: 28px;
  height: 28px;
  font-size: 13px;
  border-radius: var(--radius-sm);
}

.brand-text strong {
  display: block;
  font-size: var(--text-base);
  letter-spacing: 0.02em;
}

.side-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 var(--space-2);
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-2);
  font-size: var(--text-base);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition:
    background var(--duration) ease,
    color var(--duration) ease;
}

.nav-item:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
}

.nav-item.is-active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-weight: 600;
}

.side-foot {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.theme-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
}

.theme-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border-strong);
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.user-meta {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: var(--text-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-sub {
  font-size: var(--text-xs);
  color: var(--color-text-3);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-2);
  cursor: pointer;
  flex-shrink: 0;
}

.icon-btn:hover {
  background: var(--color-surface-3);
  color: var(--color-text);
}

.main-col {
  min-width: 0;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  height: var(--header-h);
  padding: 0 var(--space-3);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 20;
}

.topbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-base);
}

.main {
  padding: var(--space-5);
  overflow: auto;
  overflow-x: hidden;
  min-width: 0;
}

.drawer-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-surface);
}

/* 平板：主区内边距收紧 */
@media (max-width: 1024px) {
  .main {
    padding: var(--space-4);
  }
}

@media (max-width: 576px) {
  .main {
    padding: var(--space-3);
  }

  .topbar {
    padding: 0 var(--space-2);
  }
}
</style>
