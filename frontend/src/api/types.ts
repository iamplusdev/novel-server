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
}
