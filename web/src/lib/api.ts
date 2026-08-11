import { getLang } from "./i18n";

const TOKEN_KEY = "mailbus_api_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export type ApiResult<T = unknown> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number; data?: unknown; errorCode?: string };

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

/** Prefer message_zh (D21), nested result.error, then error / HTTP status. */
export function formatApiError(data: unknown, status: number): { error: string; errorCode?: string } {
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
    if (msg) {
      let error = msg;
      if (status === 502 && !/未运行|不可达|超时|404|连接/.test(msg)) {
        error = `探测失败：${msg}`;
      } else if (code && code !== msg && !msg.includes(code)) {
        error = `${msg}（${code}）`;
      }
      if (hint && !error.includes(hint)) error = `${error} · ${hint}`;
      return { error, errorCode: code };
    }
  }
  if (status === 502) return { error: "探测失败（服务未运行或不可达）", errorCode: "bad_gateway" };
  return { error: `HTTP ${status}` };
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
  _retried = false,
): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
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
      // Bad/stale localStorage token on loopback → clear once and retry without Bearer
      if (res.status === 401 && token && !_retried) {
        setToken("");
        const retryHeaders = new Headers(init.headers || {});
        if (!retryHeaders.has("Content-Type") && init.body) {
          retryHeaders.set("Content-Type", "application/json");
        }
        retryHeaders.delete("Authorization");
        return api<T>(path, { ...init, headers: retryHeaders }, true);
      }
      const formatted = formatApiError(data, res.status);
      return { ok: false, error: formatted.error, status: res.status, data, errorCode: formatted.errorCode };
    }
    return { ok: true, data: data as T, status: res.status };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "network_error", status: 0 };
  }
}
