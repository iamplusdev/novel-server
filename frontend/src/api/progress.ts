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

/** 批量刮削 */
export function startBatchScrape(payload: {
  source: string;
  only_missing: boolean;
  min_score: number;
  dry_run?: boolean;
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
