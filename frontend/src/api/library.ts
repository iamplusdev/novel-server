import { http } from "./client";
import type { LibraryReport } from "./types";

/** deep=false 快速体检（SQL）；deep=true 深度体检（含正文乱码/控制符） */
export function fetchLibraryReport(deep = false) {
  return http.get<LibraryReport>(`/api/admin/library/report?deep=${deep ? "1" : "0"}`);
}

export function mergeDuplicates(keepId: number, deleteIds: number[]) {
  return http.post<{ kept: { id: number; title: string }; deleted: unknown[] }>(
    "/api/admin/library/merge",
    { keep_id: keepId, delete_ids: deleteIds },
  );
}

export function repairAll(mode: string = "auto", bookIds?: number[]) {
  return http.post<{ results: unknown[]; count: number }>("/api/admin/library/repair", {
    mode,
    book_ids: bookIds ?? null,
  });
}

export function repairOne(bookId: number | string, mode: string = "auto") {
  return http.post<{ title?: string; actions?: string[] }>(
    `/api/admin/library/repair/${bookId}?mode=${mode}`,
  );
}

export function relocateBooks() {
  return http.post<{ moved?: number; failed?: number }>("/api/admin/library/relocate", {});
}
