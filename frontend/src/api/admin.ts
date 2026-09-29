import { http } from "./client";
import type { AdminStats, BookDetail, BookListResponse } from "./types";

/** 管理端书库 / 统计 API */
export function fetchStats() {
  return http.get<AdminStats>("/api/admin/stats");
}

export interface BookQuery {
  page?: number;
  page_size?: number;
  sort?: string;
  q?: string;
  source?: string;
  category?: string;
  tag?: string;
  status?: string;
  /** unscraped=仅未刮削 */
  scraped?: string;
}

export function fetchBooks(query: BookQuery) {
  // 展开为可序列化 query 对象，避免 TS 索引签名限制
  return http.get<BookListResponse>("/api/admin/books", { ...query });
}

export function fetchBook(id: number | string) {
  return http.get<BookDetail>(`/api/admin/books/${id}`);
}

export function updateBook(id: number | string, body: Record<string, unknown>) {
  return http.patch<BookDetail>(`/api/admin/books/${id}`, body);
}

export function deleteBook(id: number | string) {
  return http.delete<{ ok?: boolean }>(`/api/admin/books/${id}`);
}

export function uploadCover(id: number | string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return http.upload<{ ok?: boolean; cover_url?: string }>(`/api/admin/books/${id}/cover`, fd);
}
