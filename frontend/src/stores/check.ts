import { defineStore } from "pinia";
import type { LibraryReport } from "@/api/types";

/**
 * 体检报告会话内缓存（改内存态，避免 sessionStorage 5MB 上限导致大报告静默丢失）。
 * 刷新页面会清空，属预期。
 */
export const useCheckStore = defineStore("check", {
  state: () => ({
    report: null as LibraryReport | null,
    scanned: false,
  }),
  actions: {
    setReport(r: LibraryReport) {
      this.report = r;
      this.scanned = true;
    },
    clear() {
      this.report = null;
      this.scanned = false;
    },
  },
});
