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

/** Prefer message_zh (D21), then error / HTTP status. */
export function formatApiError(data: unknown, status: number): { error: string; errorCode?: string } {
  if (typeof data === "object" && data) {
    const o = data as Record<string, unknown>;
    const code = typeof o.error_code === "string" ? o.error_code : typeof o.error === "string" ? o.error : undefined;
    const zh = typeof o.message_zh === "string" ? o.message_zh : "";
    if (zh) return { error: code && code !== zh ? `${zh}（${code}）` : zh, errorCode: code };
    if (typeof o.error === "string" && o.error) return { error: o.error, errorCode: code };
    if (typeof o.message === "string" && o.message) return { error: o.message, errorCode: code };
  }
  return { error: `HTTP ${status}` };
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
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
      const formatted = formatApiError(data, res.status);
      return { ok: false, error: formatted.error, status: res.status, data, errorCode: formatted.errorCode };
    }
    return { ok: true, data: data as T, status: res.status };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "network_error", status: 0 };
  }
}
