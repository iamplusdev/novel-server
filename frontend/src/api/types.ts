/** API 层公共类型（与后端 FastAPI 响应对齐） */

export interface AuthStatus {
  setup_required: boolean;
  username: string | null;
  password_login: boolean;
}

export interface SessionInfo {
  ok: boolean;
  username: string;
  token?: string;
  expires_in?: number;
  recovery_code?: string;
}

/** 书库列表项（后端字段为 name，不是 title） */
export interface BookListItem {
  id: number;
  name: string;
  author: string;
  category: string;
  tags: string[];
  status: string;
  source: string;
  source_id: string;
  cover_path?: string | null;
  cover_url?: string | null;
  intro?: string;
  word_count?: number;
  chapter_count?: number;
  latest_chapter?: string;
  detail_url?: string;
  toc_url?: string;
  updated_at?: string;
  /** 阅读进度百分比 0–100 */
  read_percent?: number;
}

export interface BookListResponse {
  total: number;
  page: number;
  page_size: number;
  items: BookListItem[];
}

export interface CategoryNode {
  key: string;
  label: string;
  categories: string[];
}

export interface AdminStats {
  total_books: number;
  total_words: number;
  by_category: { name: string; count: number }[];
  by_status: { name: string; count: number }[];
  categories: string[];
  /** 两级分类树：书源列表 + 各自栏目 */
  category_tree: CategoryNode[];
  import?: unknown;
  public_base_url: string;
  novels_dir: string;
  database_path: string;
  covers_dir: string;
}

export interface BookDetail extends BookListItem {
  intro: string;
  source_path?: string | null;
  created_at?: string;
  cover_file?: string | null;
  source_hash?: string | null;
  category_source?: string;
  category_name?: string;
  chapters_preview?: { id: number; index: number; title: string }[];
  /** 续读章节序号（-1 表示未读） */
  read_chapter_index?: number;
  read_at?: string;
}

/** 站外刮削命中项 */
export interface ScrapeHit {
  source: string;
  source_id: string;
  name: string;
  author: string;
  latest_chapter?: string;
  cover_url?: string;
  url?: string;
  intro?: string;
  status?: string;
  category?: string;
  word_count?: number;
  tags?: string[];
}

export interface ScrapeSearchResponse {
  source: string;
  source_key: string;
  query: string;
  items: ScrapeHit[];
  count: number;
}

/** 本地导入实时状态 */
export interface ImportStatus {
  running: boolean;
  last?: {
    added: string[];
    updated: string[];
    skipped: string[];
    failed: string[];
    summary: string;
    finished_at: string;
  } | null;
  total?: number;
  done?: number;
  current?: string;
  percent?: number;
  added_n?: number;
  updated_n?: number;
  skipped_n?: number;
  failed_n?: number;
  recent?: string[];
  cancel_requested?: boolean;
}

/** 批量刮削实时状态 */
export interface BatchStatus {
  running: boolean;
  total?: number;
  done?: number;
  matched?: number;
  skipped?: number;
  failed?: number;
  log?: { time: string; message: string }[];
  last_error?: string;
  cancel_requested?: boolean;
  dry_run?: boolean;
}

/** 书库体检报告 */
export interface DupGroup {
  title: string;
  author: string;
  count: number;
  keep_id: number;
  books: {
    id: number;
    source_path?: string | null;
    source?: string | null;
    source_id?: string | null;
    chapter_count?: number;
    word_count?: number;
    cover_file?: string | null;
  }[];
}

export interface LibraryIssue {
  book_id: number;
  title: string;
  kind: string;
  message: string;
  detail?: string;
}

export interface LibraryReport {
  duplicates: DupGroup[];
  issues: LibraryIssue[];
  duplicate_groups: number;
  issue_count: number;
}
