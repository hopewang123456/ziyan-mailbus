import { useEffect, useRef, useState } from "react";
import { api, type ApiResult } from "./api";

/**
 * 唯一屏幕身份实现：`localStorage["mailbus.screen"]` 只存 screen_id + secret，
 * 其余状态（在线、版本、团队绑定）一律从服务端拉取。
 * 心跳/离线使用 `X-Screen-Secret` 头（后端 B6 切换，联调前由 mock 兜底）。
 */

export const SCREEN_STORAGE_KEY = "mailbus.screen";

export interface ScreenCredential {
  screen_id: string;
  secret: string;
}

function readCredential(storageKey: string): ScreenCredential | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { screen_id?: unknown; secret?: unknown };
    if (typeof parsed?.screen_id !== "string" || !parsed.screen_id) return null;
    return {
      screen_id: parsed.screen_id,
      secret: typeof parsed.secret === "string" ? parsed.secret : "",
    };
  } catch {
    return null;
  }
}

function writeCredential(storageKey: string, credential: ScreenCredential): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify(credential));
  } catch {
    // 存储不可用时仅本次会话有效
  }
}

export function newScreenId(prefix = "screen"): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
      : Math.random().toString(36).slice(2, 14);
  return `${prefix}_${random}`;
}

export function getScreenCredential(storageKey = SCREEN_STORAGE_KEY): ScreenCredential | null {
  return readCredential(storageKey);
}

/** 首次进入时生成稳定标识并落盘；刷新后复用。 */
export function getOrCreateScreenId(storageKey = SCREEN_STORAGE_KEY, prefix = "screen"): string {
  const existing = readCredential(storageKey);
  if (existing) return existing.screen_id;
  const screen_id = newScreenId(prefix);
  writeCredential(storageKey, { screen_id, secret: "" });
  return screen_id;
}

export function saveScreenCredential(
  credential: ScreenCredential,
  storageKey = SCREEN_STORAGE_KEY,
): void {
  writeCredential(storageKey, credential);
}

export function clearScreenIdentity(storageKey = SCREEN_STORAGE_KEY): void {
  try {
    localStorage.removeItem(storageKey);
  } catch {
    // 忽略
  }
}

export interface ScreenHeartbeatPayload {
  floor_id?: string | null;
  seat_id?: string | null;
}

export function sendScreenHeartbeat(
  basePath: string,
  screenId: string,
  secret: string,
  payload: ScreenHeartbeatPayload = {},
): Promise<ApiResult<unknown>> {
  return api(`${basePath}/screens/${encodeURIComponent(screenId)}/heartbeat`, {
    method: "POST",
    headers: secret ? { "X-Screen-Secret": secret } : undefined,
    body: JSON.stringify(payload),
  });
}

/** 离线使用 keepalive，便于页面关闭时仍能发出。 */
export function leaveScreen(
  basePath: string,
  screenId: string,
  secret: string,
  payload: ScreenHeartbeatPayload = {},
): void {
  try {
    void fetch(`${basePath}/screens/${encodeURIComponent(screenId)}/leave`, {
      method: "POST",
      keepalive: true,
      headers: {
        "Content-Type": "application/json",
        ...(secret ? { "X-Screen-Secret": secret } : {}),
      },
      body: JSON.stringify(payload),
    }).catch(() => undefined);
  } catch {
    // 页面卸载阶段忽略
  }
}

function readSecret(record: Record<string, unknown>): string {
  const value = record.screen_secret ?? record.secret;
  return typeof value === "string" ? value : "";
}

function readScreenId(record: Record<string, unknown>, fallback: string): string {
  return typeof record.screen_id === "string" && record.screen_id
    ? record.screen_id
    : fallback;
}

export interface ScreenSessionOptions {
  enabled?: boolean;
  name?: string;
  /** 公开端 `/api/public/collab`，管理端 `/api/collab`。 */
  basePath?: string;
  storageKey?: string;
  heartbeatMs?: number;
  /** 心跳时携带的当前楼层/工位，用 getter 保持最新值。 */
  getPayload?: () => ScreenHeartbeatPayload;
}

export interface ScreenSession {
  screenId: string;
  registered: boolean;
  online: boolean;
}

/**
 * 登记 + 心跳 + 离线；返回本屏标识。
 * 已有 `screen_id + secret` 且匹配时服务端复用，不覆盖；新建才回显一次密钥。
 */
export function useScreenSession(options: ScreenSessionOptions = {}): ScreenSession {
  const {
    enabled = true,
    name = "mailbus 大屏",
    basePath = "/api/public/collab",
    storageKey = SCREEN_STORAGE_KEY,
    heartbeatMs = 30_000,
  } = options;
  const [screenId, setScreenId] = useState(() => getOrCreateScreenId(storageKey));
  const [registered, setRegistered] = useState(false);
  const [online, setOnline] = useState(false);
  const payloadRef = useRef(options.getPayload);
  payloadRef.current = options.getPayload;

  useEffect(() => {
    setScreenId(getOrCreateScreenId(storageKey));
  }, [storageKey]);

  useEffect(() => {
    if (!enabled) {
      setRegistered(false);
      setOnline(false);
      return;
    }

    let disposed = false;
    let heartbeat = 0;
    let currentId = screenId;
    let secret = readCredential(storageKey)?.secret ?? "";

    const register = async (): Promise<boolean> => {
      const result = await api<Record<string, unknown>>(`${basePath}/screens`, {
        method: "POST",
        body: JSON.stringify({
          screen_id: currentId,
          name,
          ...(secret ? { secret } : {}),
          ...(payloadRef.current?.() ?? {}),
        }),
      });
      if (disposed) return false;
      if (result.ok) {
        const record = (result.data ?? {}) as Record<string, unknown>;
        currentId = readScreenId(record, currentId);
        const issued = readSecret(record);
        if (issued) {
          secret = issued;
          writeCredential(storageKey, { screen_id: currentId, secret });
        }
        if (!secret) return false;
        if (currentId !== screenId) setScreenId(currentId);
        return true;
      }
      return false;
    };

    const beat = async () => {
      if (disposed || !secret) return;
      const result = await sendScreenHeartbeat(
        basePath,
        currentId,
        secret,
        payloadRef.current?.() ?? {},
      );
      if (disposed) return;
      const ok = result.ok;
      setOnline(ok);
      // 密钥失效：清掉本地身份，下次进入重新登记
      if (!ok && (result.status === 403 || result.status === 404)) {
        clearScreenIdentity(storageKey);
      }
    };

    const leave = () => {
      if (!secret) return;
      leaveScreen(basePath, currentId, secret, payloadRef.current?.() ?? {});
    };

    void (async () => {
      let ok = await register();
      if (disposed) return;
      if (!ok && !secret) {
        // 本机无密钥且服务端未回显：换新标识重新登记一次
        currentId = newScreenId();
        writeCredential(storageKey, { screen_id: currentId, secret: "" });
        ok = await register();
        if (disposed) return;
      }
      if (!ok) return;
      setRegistered(true);
      setOnline(true);
      void beat();
      heartbeat = window.setInterval(() => void beat(), heartbeatMs);
    })();

    window.addEventListener("pagehide", leave);
    return () => {
      disposed = true;
      window.clearInterval(heartbeat);
      window.removeEventListener("pagehide", leave);
      leave();
      setRegistered(false);
      setOnline(false);
    };
  }, [enabled, basePath, storageKey, name, heartbeatMs, screenId]);

  return { screenId, registered, online };
}
