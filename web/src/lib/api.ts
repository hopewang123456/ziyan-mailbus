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
      const method = String(init.method || "GET").toUpperCase();
      const isRead = method === "GET" || method === "HEAD";
      // 读请求：过期/错误 Bearer 会 401（presented token must match）→ 清掉后无 Bearer 重试
      if (res.status === 401 && token && !_retried && isRead) {
        setToken("");
        const retryHeaders = new Headers(init.headers || {});
        if (!retryHeaders.has("Content-Type") && init.body) {
          retryHeaders.set("Content-Type", "application/json");
        }
        retryHeaders.delete("Authorization");
        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("mailbus:auth-required", {
              detail: { status: 401, path, hadToken: true, stale: true },
            }),
          );
        }
        return api<T>(path, { ...init, headers: retryHeaders }, true);
      }
      if (res.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("mailbus:auth-required", {
            detail: { status: 401, path, hadToken: Boolean(token), write: !isRead },
          }),
        );
      }
      const formatted = formatApiError(data, res.status);
      return { ok: false, error: formatted.error, status: res.status, data, errorCode: formatted.errorCode };
    }
    return { ok: true, data: data as T, status: res.status };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "network_error", status: 0 };
  }
}


/* ── 管理者协调台 ─────────────────────────────── */
export type ManagerCurrentStep = {
  step_id?: string;
  role_type?: number | string;
  role_zh?: string;
  to_agent?: string;
  state?: string;
  report?: string;
};

export type ManagerPendingItem = {
  task_id?: string;
  summary?: string;
  task_type?: string;
  initiator?: string;
  tier?: string;
  priority?: number;
  status?: string;
  fsm_state?: string;
  fsm_substate?: string;
  fsm_reason?: string;
  join_pending?: { group?: string; join_role_type?: number; join_gate?: string };
  bucket?: "plan_approval" | "acceptance" | "coordination" | "";
  current_step?: ManagerCurrentStep;
  updated_at?: string;
  suggested_actions?: string[];
};

export type ManagerPendingResp = {
  total?: number;
  counts?: { plan_approval: number; acceptance: number; coordination: number };
  items?: ManagerPendingItem[];
};

export const getManagerPending = () => api<ManagerPendingResp>("/api/manager/pending");

export const postTaskFsm = (id: string, action: string, body: Record<string, unknown> = {}) =>
  api(`/api/tasks/${encodeURIComponent(id)}/fsm/${encodeURIComponent(action)}`, {
    method: "POST",
    body: JSON.stringify(body),
  });

/** 设置保存响应里的 effects[] → 追加到成功文案 */
export function formatSettingsEffects(data: unknown, base: string): string {
  if (!data || typeof data !== "object") return base;
  const raw = (data as { effects?: unknown }).effects;
  if (!Array.isArray(raw) || raw.length === 0) return base;
  const bits: string[] = [];
  for (const e of raw.slice(0, 5)) {
    if (typeof e === "string") {
      bits.push(e);
      continue;
    }
    if (!e || typeof e !== "object") continue;
    const o = e as Record<string, unknown>;
    const op = String(o.op || o.kind || "effect");
    const ok = o.ok === false ? "fail" : "ok";
    const id = o.instance_id || o.section || o.error || "";
    bits.push(id ? `${op}:${ok}:${id}` : `${op}:${ok}`);
  }
  return bits.length ? `${base} · ${bits.join("; ")}` : base;
}
