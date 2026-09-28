/** API 层公共类型（与后端 FastAPI 响应对齐，按阶段补全） */

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

export interface BookListItem {
  id: number;
  title: string;
  author: string;
  category: string;
  source?: string | null;
  source_id?: string | null;
  cover_url?: string | null;
  word_count?: number;
  chapter_count?: number;
  status?: string;
  tags?: string;
  updated_at?: string;
}

export interface BookListResponse {
  total: number;
  page: number;
  page_size: number;
  items: BookListItem[];
}

export interface ApiErrorBody {
  detail?: string | { msg?: string }[];
}
