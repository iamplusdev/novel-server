import { createApp } from "vue";
import { createPinia } from "pinia";
// Element Plus 组件与 API 由 unplugin-vue-components 按需引入；这里仅保留全局样式
import "element-plus/dist/index.css";
import "element-plus/theme-chalk/dark/css-vars.css";
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
