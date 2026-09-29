/**
 * 统一 fetch 封装：
 * - 同源 Cookie 会话（credentials: include）
 * - 非 2xx 抛 ApiError
 * - 401 由调用方/拦截逻辑处理跳登录
 */

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined | null>;
  skipAuthRedirect?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  if (!query) return path;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    // 丢弃 NaN/Infinity，避免后端整型字段收到 "NaN" 导致 422
    if (typeof v === "number" && !Number.isFinite(v)) continue;
    sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path;
}

/** 业务错误文案提取 */
function extractMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((x) => (x && typeof x === "object" && "msg" in x ? String(x.msg) : JSON.stringify(x)))
        .join("; ");
    }
  }
  return fallback;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, query } = options;
  const url = buildUrl(path, query);

  const init: RequestInit = {
    method,
    credentials: "include",
    headers: { ...headers },
  };

  if (body !== undefined) {
    if (body instanceof FormData) {
      init.body = body;
    } else {
      init.headers = { "Content-Type": "application/json", ...init.headers };
      init.body = JSON.stringify(body);
    }
  }

  const res = await fetch(url, init);
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, extractMessage(data, `请求失败（${res.status}）`));
  }
  return data as T;
}

export const http = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    request<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};
