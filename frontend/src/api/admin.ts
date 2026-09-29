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

/** 批量删除（书库多选） */
export function batchDeleteBooks(ids: number[]) {
  return http.post<{ ok: boolean; deleted_count: number; deleted: string[]; ids: number[] }>(
    "/api/admin/books/batch/delete",
    { ids },
  );
}

/** 写入阅读进度（百分比 0–100） */
export function updateReadProgress(
  id: number | string,
  body: { percent: number; chapter_index?: number },
) {
  return http.put<{
    ok: boolean;
    id: number;
    read_percent: number;
    read_chapter_index: number;
    read_at: string;
  }>(`/api/admin/books/${id}/progress`, body);
}

export function uploadCover(id: number | string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return http.upload<{ ok?: boolean; cover_url?: string }>(`/api/admin/books/${id}/cover`, fd);
}

/** 阅读器：完整目录（分页，page_size 默认 500） */
export function fetchBookChapters(bookId: number | string, page = 1, pageSize = 500) {
  return http.get<{
    book_id: number;
    book_name: string;
    total: number;
    page: number;
    page_size: number;
    items: { id: number; index: number; name: string; title: string }[];
  }>(`/api/books/${bookId}/chapters`, { page, page_size: pageSize });
}

export interface TocChapter {
  id: number;
  index: number;
  title: string;
}

/** 拉取全部目录（按 total 翻页），返回列表 + 真实总章数 */
export async function fetchAllBookChapters(bookId: number | string): Promise<{
  items: TocChapter[];
  total: number;
}> {
  const pageSize = 500;
  const first = await fetchBookChapters(bookId, 1, pageSize);
  const items: TocChapter[] = (first.items || []).map((c) => ({
    id: c.id,
    index: c.index,
    title: c.title || c.name || "",
  }));
  const total = Number(first.total) || items.length;
  let page = 2;
  while (items.length < total) {
    const next = await fetchBookChapters(bookId, page, pageSize);
    const chunk = next.items || [];
    if (!chunk.length) break;
    for (const c of chunk) {
      items.push({ id: c.id, index: c.index, title: c.title || c.name || "" });
    }
    page += 1;
  }
  return { items, total };
}

/** 阅读器：章节正文 */
export function fetchChapterContent(bookId: number | string, chapterId: number | string) {
  return http.get<{
    id: number;
    book_id: number;
    index: number;
    title: string;
    content: string;
  }>(`/api/books/${bookId}/chapters/${chapterId}`);
}
