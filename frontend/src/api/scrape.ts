import { http } from "./client";
import type { BookDetail, ScrapeHit, ScrapeSearchResponse } from "./types";

/** 单本刮削 API */
export function scrapeSearch(payload: {
  keyword: string;
  source: string;
  limit?: number;
}) {
  return http.post<ScrapeSearchResponse>("/api/admin/scrape/search", payload);
}

export function scrapeDetail(payload: {
  source: string;
  source_book_id: string;
}) {
  return http.post<ScrapeHit>("/api/admin/scrape/detail", payload);
}

export function scrapeApply(bookId: number | string, payload: Record<string, unknown>) {
  return http.post<BookDetail>(`/api/admin/scrape/books/${bookId}/apply`, payload);
}

/** 判断关键词是否像书号/详情链接，应直接拉详情 */
export function looksLikeBookId(keyword: string): boolean {
  return (
    /^\d{5,24}$/.test(keyword) ||
    /qidian\.com\/book\/\d+|fanqienovel\.com\/page\/\d+|zongheng\.com\/(?:detail|book)\/\d+/.test(
      keyword,
    )
  );
}

/** 去掉不适合写入的标签（字数、连载/完结） */
export function cleanHintTags(tags?: string[] | null): string[] {
  return (tags || []).filter((t) => t && !/字$/.test(t) && t !== "连载" && t !== "完结");
}

export const SCRAPE_SOURCE_OPTS = [
  { value: "qidian", label: "起点" },
  { value: "fanqie", label: "番茄" },
  { value: "zongheng", label: "纵横" },
] as const;
