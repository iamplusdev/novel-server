import { createRouter, createWebHistory } from "vue-router";
import type { RouteRecordRaw } from "vue-router";

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
    ],
  },
  // SPA fallback：未知路径回书库
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
