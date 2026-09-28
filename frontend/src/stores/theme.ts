import { defineStore } from "pinia";

export type ThemeMode = "auto" | "light" | "dark";

const THEME_KEY = "novel_theme_mode";

function applyTheme(mode: ThemeMode) {
  const dark =
    mode === "dark" ||
    (mode === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** 主题：与旧版 localStorage 键名保持一致 */
export const useThemeStore = defineStore("theme", {
  state: () => ({
    mode: (localStorage.getItem(THEME_KEY) as ThemeMode) || "auto",
  }),
  actions: {
    init() {
      applyTheme(this.mode);
      // 跟随系统时监听切换
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (this.mode === "auto") applyTheme("auto");
      });
    },
    setMode(mode: ThemeMode) {
      this.mode = mode;
      localStorage.setItem(THEME_KEY, mode);
      applyTheme(mode);
    },
  },
});
