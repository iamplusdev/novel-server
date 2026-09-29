import { http } from "./client";
import type { BatchStatus, ImportStatus } from "./types";

/** 本地导入 */
export function startImport() {
  return http.post<{ started: boolean; mode: string; import: ImportStatus }>(
    "/api/admin/import?mode=local",
  );
}

export function cancelImport() {
  return http.post<{ ok: boolean; import: ImportStatus }>("/api/admin/import/cancel");
}

export function fetchImportStatus() {
  return http.get<ImportStatus>("/api/admin/import/status");
}

export interface ImportLogItem {
  id: number;
  started_at: string;
  finished_at: string;
  mode: string;
  summary: string;
  total: number;
  added_n: number;
  updated_n: number;
  skipped_n: number;
  failed_n: number;
  detail: {
    added: string[];
    updated: string[];
    skipped: string[];
    failed: string[];
    recent: string[];
  };
  /** 仅新增列表（历史只记录新增时使用） */
  added_list?: string[];
}

/** 历史导入日志；date=YYYY-MM-DD */
export function fetchImportLogs(date?: string, limit = 50) {
  return http.get<{ items: ImportLogItem[]; total: number }>("/api/admin/import/logs", {
    date: date || undefined,
    limit,
  });
}

/** 批量刮削：source="all" 按起点→番茄→纵横顺序，命中即停；book_ids 非空则只刮选中书 */
export function startBatchScrape(payload: {
  source: string;
  only_missing: boolean;
  min_score: number;
  book_ids?: number[];
  /** api | chrome | auto */
  mode?: string;
}) {
  return http.post<{ started: boolean; status: BatchStatus }>(
    "/api/admin/scrape/batch/start",
    payload,
  );
}

export function cancelBatchScrape() {
  return http.post<{ ok: boolean; status: BatchStatus }>("/api/admin/scrape/batch/cancel");
}

export function fetchBatchStatus() {
  return http.get<BatchStatus>("/api/admin/scrape/batch/status");
}

export const IMPORT_STREAM_URL = "/api/admin/import/stream";
export const BATCH_STREAM_URL = "/api/admin/scrape/batch/stream";
