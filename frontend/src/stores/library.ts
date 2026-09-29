import { defineStore } from "pinia";
import { fetchBooks, fetchStats } from "@/api/admin";
import type { AdminStats, BookListItem } from "@/api/types";

/** 书源行选项（与旧版 SOURCE_OPTS 一致） */
export const SOURCE_OPTS = ["", "起点", "番茄", "纵横"] as const;

interface LibraryState {
  stats: AdminStats | null;
  items: BookListItem[];
  total: number;
  page: number;
  pageSize: number;
  sort: string;
  q: string;
  source: string;
  category: string;
  /** true=仅未刮削 */
  onlyUnscraped: boolean;
  loading: boolean;
  /** 请求序号：丢弃过期响应 */
  reqSeq: number;
}

export const useLibraryStore = defineStore("library", {
  state: (): LibraryState => ({
    stats: null,
    items: [],
    total: 0,
    page: 1,
    pageSize: 24,
    sort: localStorage.getItem("novel_sort") || "updated",
    q: "",
    source: "",
    category: "",
    onlyUnscraped: false,
    loading: false,
    reqSeq: 0,
  }),
  getters: {
    totalPages: (s) => Math.max(1, Math.ceil(s.total / s.pageSize)),
    /** 当前书源下的分类列表；默认展示「起点」分类，避免并集过长 */
    categoryNames: (s): string[] => {
      const tree = s.stats?.category_tree || [];
      const byKey = new Map(tree.map((n) => [n.key, n.categories]));
      if (s.source === "番茄" && byKey.has("番茄")) return byKey.get("番茄")!.slice();
      if (s.source === "纵横" && byKey.has("纵横")) return byKey.get("纵横")!.slice();
      return (byKey.get("起点") || byKey.get("") || []).slice();
    },
  },
  actions: {
    async loadStats() {
      this.stats = await fetchStats();
    },
    async loadBooks() {
      const seq = ++this.reqSeq;
      this.loading = true;
      try {
        // 整型兜底：避免 NaN/小数进入 query 导致 422
        const page = Math.max(1, Math.floor(Number(this.page) || 1));
        const pageSize = Math.min(200, Math.max(1, Math.floor(Number(this.pageSize) || 24)));
        const data = await fetchBooks({
          page,
          page_size: pageSize,
          sort: this.sort,
          q: this.q || undefined,
          source: this.source || undefined,
          category: this.category || undefined,
          scraped: this.onlyUnscraped ? "unscraped" : undefined,
        });
        if (seq !== this.reqSeq) return;
        this.page = page;
        this.pageSize = pageSize;
        this.items = data.items || [];
        this.total = data.total || 0;
        const pages = Math.max(1, Math.ceil(this.total / this.pageSize));
        if (this.page > pages) this.page = pages;
      } finally {
        if (seq === this.reqSeq) this.loading = false;
      }
    },
    /** 切换筛选后回到第一页并拉取 */
    async applyFilter(
      patch: Partial<
        Pick<LibraryState, "q" | "source" | "category" | "sort" | "onlyUnscraped">
      >,
    ) {
      if (patch.source !== undefined && patch.source !== this.source) {
        this.source = patch.source;
        this.category = "";
      } else if (patch.category !== undefined) {
        this.category = patch.category;
      }
      if (patch.q !== undefined) this.q = patch.q;
      if (patch.onlyUnscraped !== undefined) this.onlyUnscraped = patch.onlyUnscraped;
      if (patch.sort !== undefined) {
        this.sort = patch.sort;
        localStorage.setItem("novel_sort", patch.sort);
      }
      this.page = 1;
      await this.loadBooks();
    },
    async gotoPage(p: number) {
      const pages = this.totalPages;
      const raw = Math.floor(Number(p) || 1);
      const next = Math.min(pages, Math.max(1, raw));
      if (next === this.page) return;
      this.page = next;
      await this.loadBooks();
    },
  },
});
