import { getLang } from "./i18n";

const TOKEN_KEY = "mailbus_api_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mailbus:auth-ok"));
    }
  } else localStorage.removeItem(TOKEN_KEY);
}

/**
 * 临时通用类型（B1.5 契约桩导出前唯一允许手写的三个）。
 * 领域 DTO 一律等待 `npm run gen:types` 生成，不在前端手写。
 */
export interface ApiError {
  status: number;
  error_code: string;
  message_zh: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Ok {
  ok: true;
}

export type ErrorKind =
  | "validation"
  | "auth"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "gone"
  | "rate_limited"
  | "unavailable"
  | "network"
  | "unknown";

export function classifyStatus(status: number): ErrorKind {
  if (status === 0) return "network";
  if (status === 400 || status === 422) return "validation";
  if (status === 401) return "auth";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 410) return "gone";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "unavailable";
  return "unknown";
}

export type ApiResult<T = unknown> =
  | { ok: true; data: T; status: number }
  | {
      ok: false;
      error: string;
      status: number;
      kind: ErrorKind;
      data?: unknown;
      errorCode?: string;
      fields?: Record<string, string>;
    };

function digError(o: Record<string, unknown>): string {
  const lang = getLang();
  const zh = typeof o.message_zh === "string" ? o.message_zh : "";
  const en = typeof o.message === "string" ? o.message : "";
  if (lang === "zh" && zh) return zh;
  if (en) return en;
  if (zh) return zh;
  if (typeof o.error === "string" && o.error) return o.error;
  const result = o.result;
  if (typeof result === "object" && result) {
    const r = result as Record<string, unknown>;
    if (typeof r.error === "string" && r.error) return r.error;
    if (typeof r.message === "string" && r.message) return r.message;
    if (typeof r.detail === "string" && r.detail) return r.detail;
  }
  if (typeof o.detail === "string" && o.detail) return o.detail;
  return "";
}

/** FastAPI / 后端常见的字段级错误结构归一。 */
function digFields(o: Record<string, unknown>): Record<string, string> | undefined {
  const raw = o.fields ?? o.errors;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const fields: Record<string, string> = {};
    for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
      if (typeof value === "string") fields[key] = value;
    }
    return Object.keys(fields).length ? fields : undefined;
  }
  if (Array.isArray(o.detail)) {
    const fields: Record<string, string> = {};
    for (const item of o.detail) {
      if (!item || typeof item !== "object") continue;
      const entry = item as Record<string, unknown>;
      const loc = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
      const msg = typeof entry.msg === "string" ? entry.msg : "";
      if (loc && msg) fields[loc] = msg;
    }
    return Object.keys(fields).length ? fields : undefined;
  }
  return undefined;
}

/** Prefer message_zh (D21), nested result.error, then error / HTTP status. */
export function formatApiError(
  data: unknown,
  status: number,
): { error: string; errorCode?: string; fields?: Record<string, string> } {
  if (typeof data === "object" && data) {
    const o = data as Record<string, unknown>;
    const code =
      typeof o.error_code === "string"
        ? o.error_code
        : typeof o.error === "string"
          ? o.error
          : undefined;
    const msg = digError(o);
    const hint = typeof o.hint === "string" ? o.hint : "";
    const fields = digFields(o);
    if (msg) {
      let error = msg;
      if (status === 502 && !/未运行|不可达|超时|404|连接/.test(msg)) {
        error = `探测失败：${msg}`;
      } else if (code && code !== msg && !msg.includes(code)) {
        error = `${msg}（${code}）`;
      }
      if (hint && !error.includes(hint)) error = `${error} · ${hint}`;
      return { error, errorCode: code, fields };
    }
    if (fields) return { error: `HTTP ${status}`, errorCode: code, fields };
  }
  if (status === 502) return { error: "探测失败（服务未运行或不可达）", errorCode: "bad_gateway" };
  if (status === 0) return { error: "网络不可用" };
  return { error: `HTTP ${status}` };
}

export function isFormData(body: BodyInit | null | undefined): boolean {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

function buildHeaders(init: RequestInit, extra?: HeadersInit): Headers {
  const headers = new Headers(init.headers || {});
  if (extra) {
    const more = new Headers(extra);
    more.forEach((value, key) => headers.set(key, value));
  }
  // FormData 必须让浏览器自动带 boundary，不能手写 Content-Type
  if (!headers.has("Content-Type") && init.body && !isFormData(init.body)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
  _retried = false,
): Promise<ApiResult<T>> {
  const headers = buildHeaders(init);
  try {
    const res = await fetch(path, { ...init, headers });
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
      const method = String(init.method || "GET").toUpperCase();
      const isRead = method === "GET" || method === "HEAD";
      // 读请求：过期/错误 Bearer 会 401（presented token must match）→ 清掉后无 Bearer 重试
      if (res.status === 401 && getToken() && !_retried && isRead) {
        const token = getToken();
        setToken("");
        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("mailbus:auth-required", {
              detail: { status: 401, path, hadToken: Boolean(token), stale: true },
            }),
          );
        }
        return api<T>(path, init, true);
      }
      if (res.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("mailbus:auth-required", {
            detail: {
              status: 401,
              path,
              hadToken: Boolean(getToken()),
              write: !isRead,
            },
          }),
        );
      }
      const formatted = formatApiError(data, res.status);
      // 写操作失败必须可见（此前 400/500 只落到页面角落的小字）
      if (!isRead && typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("mailbus:write-failed", {
            detail: { path, status: res.status, error: formatted.error, method },
          }),
        );
      }
      return {
        ok: false,
        error: formatted.error,
        status: res.status,
        kind: classifyStatus(res.status),
        data,
        errorCode: formatted.errorCode,
        fields: formatted.fields,
      };
    }
    return { ok: true, data: data as T, status: res.status };
  } catch (e) {
    const method = String(init.method || "GET").toUpperCase();
    const aborted = e instanceof DOMException && e.name === "AbortError";
    const msg = aborted ? "请求已取消" : e instanceof Error ? e.message : "network_error";
    if (!aborted && method !== "GET" && method !== "HEAD" && typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("mailbus:write-failed", {
          detail: { path, status: 0, error: msg, method },
        }),
      );
    }
    return { ok: false, error: msg, status: 0, kind: aborted ? "unknown" : "network" };
  }
}

/**
 * 下载签名 URL：410 表示链接过期，允许重签一次后重试。
 * `resign` 由领域层提供（24h 签名契约冻结后接入），F0 只固定调用形状。
 */
export async function downloadFile(
  path: string,
  options: { filename?: string; resign?: () => Promise<string> } = {},
): Promise<ApiResult<Blob>> {
  const attempt = async (target: string, allowResign: boolean): Promise<ApiResult<Blob>> => {
    try {
      const res = await fetch(target, {
        headers: buildHeaders({}),
      });
      if (res.status === 410 && allowResign && options.resign) {
        const next = await options.resign();
        return attempt(next, false);
      }
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        let data: unknown = text;
        try {
          data = text ? JSON.parse(text) : null;
        } catch {
          // 保留原始文本
        }
        const formatted = formatApiError(data, res.status);
        return {
          ok: false,
          error: formatted.error,
          status: res.status,
          kind: classifyStatus(res.status),
          data,
          errorCode: formatted.errorCode,
        };
      }
      const blob = await res.blob();
      if (options.filename && typeof document !== "undefined") {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = options.filename;
        link.click();
        URL.revokeObjectURL(url);
      }
      return { ok: true, data: blob, status: res.status };
    } catch (e) {
      return {
        ok: false,
        error: e instanceof Error ? e.message : "network_error",
        status: 0,
        kind: "network",
      };
    }
  };
  return attempt(path, true);
}
