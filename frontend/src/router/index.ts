import { createRouter, createWebHistory } from "vue-router";
import type { RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

/** 路由表：与旧 UI 视图一一对应，具体页面按阶段逐步落地 */
const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("@/layouts/AdminLayout.vue"),
    children: [
      {
        path: "",
        name: "library",
        component: () => import("@/views/LibraryView.vue"),
        meta: { title: "书库" },
      },
      {
        path: "import",
        name: "import",
        component: () => import("@/views/ImportView.vue"),
        meta: { title: "导入" },
      },
      {
        path: "check",
        name: "check",
        component: () => import("@/views/CheckView.vue"),
        meta: { title: "体检" },
      },
      {
        path: "api-docs",
        name: "api-docs",
        component: () => import("@/views/ApiView.vue"),
        meta: { title: "API / 书源" },
      },
      {
        path: "settings",
        name: "settings",
        component: () => import("@/views/SettingsView.vue"),
        meta: { title: "设置" },
      },
      {
        path: "books/:id",
        name: "book-detail",
        component: () => import("@/views/BookDetailView.vue"),
        meta: { title: "书籍详情" },
      },
      {
        path: "books/:id/read",
        name: "book-read",
        component: () => import("@/views/ReaderView.vue"),
        meta: { title: "阅读" },
      },
    ],
  },
  // SPA fallback：未知路径回书库
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

/** 会话守卫：未登录进 login；已登录访问 login 回书库 */
router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.checked) {
    try {
      await auth.tryRestore();
    } catch {
      /* 网络异常时放行到登录页展示错误 */
    }
  }
  if (to.meta.public) {
    if (auth.isAuthed && to.name === "login") return { name: "library" };
    return true;
  }
  if (!auth.isAuthed) return { name: "login" };
  return true;
});

export default router;
