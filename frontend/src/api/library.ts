import { http } from "./client";
import type { LibraryReport } from "./types";

export function fetchLibraryReport() {
  return http.get<LibraryReport>("/api/admin/library/report");
}

export function mergeDuplicates(keepId: number, deleteIds: number[]) {
  return http.post<{ kept: { id: number; title: string }; deleted: unknown[] }>(
    "/api/admin/library/merge",
    { keep_id: keepId, delete_ids: deleteIds },
  );
}

export function repairAll(mode: string = "auto") {
  return http.post<{ results: unknown[]; count: number }>("/api/admin/library/repair", { mode });
}

export function repairOne(bookId: number | string, mode: string = "auto") {
  return http.post<{ title?: string; actions?: string[] }>(
    `/api/admin/library/repair/${bookId}?mode=${mode}`,
  );
}

export function relocateBooks() {
  return http.post<{ moved?: number; failed?: number }>("/api/admin/library/relocate", {});
}
