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
  | { ok: false; error: string; status: number; data?: unknown };

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
      const err =
        typeof data === "object" && data && "error" in data
          ? String((data as { error: string }).error)
          : `HTTP ${res.status}`;
      return { ok: false, error: err, status: res.status, data };
    }
    return { ok: true, data: data as T, status: res.status };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "network_error", status: 0 };
  }
}
