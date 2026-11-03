import { createApp } from "vue";
import { createPinia } from "pinia";
// 顺序：先补 Element Plus 按需样式，再加载项目全局样式覆盖主题变量

// Element Plus 组件样式由 unplugin-vue-components 按需引入；
// 这里补上通过 JS 直接调用的 Message / MessageBox / Loading（v-loading）样式。
import "element-plus/theme-chalk/dark/css-vars.css";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import "element-plus/es/components/loading/style/css";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import "./style.css";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
app.use(router);

// 会话失效统一跳登录（api/client 在 401 时派发）
window.addEventListener("app:unauthorized", () => {
  const auth = useAuthStore(pinia);
  auth.username = "";
  auth.token = "";
  if (router.currentRoute.value.name !== "login") {
    void router.replace({ name: "login" });
  }
});

app.mount("#app");
