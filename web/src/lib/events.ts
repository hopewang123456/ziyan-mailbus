import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "./api";

/**
 * 唯一 SSE 实现：fetch + 分帧 + 心跳看门狗 + 指数退避 + 可见性恢复。
 * 公开流（匿名/白名单事件）与登录流（Bearer/全量事件）共用同一套 Runner。
 */

export interface SseEvent {
  event: string;
  data: string;
}

export type StreamState = "idle" | "connecting" | "live" | "lost" | "expired";

const RETRY_MS = [1000, 2000, 4000, 8000, 15000];
/** 后端每 15 秒发一次心跳；连续 40 秒无数据即判定半开，主动断开重连。 */
const IDLE_TIMEOUT_MS = 40_000;
const WATCHDOG_TICK_MS = 5_000;

/** 兼容旧调用：只要 data，不要 event 名。 */
export function createSseFeed(onData: (data: string) => void) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    for (;;) {
      const match = /\r?\n\r?\n/.exec(buffer);
      if (!match || match.index === undefined) break;
      const frame = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (!line || line.startsWith(":")) continue;
        if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) onData(data.join("\n"));
    }
    if (buffer.length > 1_000_000) buffer = "";
  };
}

/** 保留 event 名称的分帧解析；忽略 `: ping` 注释行。 */
export function createEventFeed(onEvent: (event: SseEvent) => void) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    for (;;) {
      const match = /\r?\n\r?\n/.exec(buffer);
      if (!match || match.index === undefined) break;
      const frame = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (!line || line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) onEvent({ event, data: data.join("\n") });
    }
    if (buffer.length > 1_000_000) buffer = "";
  };
}

export interface StreamSnapshot {
  overview: Record<string, unknown>;
  log: unknown[];
}

/** 解析 /api/stream 的 data 负载；结构不符或坏 JSON 返回 null。 */
export function parseStreamPayload(data: string): StreamSnapshot | null {
  try {
    const parsed: unknown = JSON.parse(data);
    if (!parsed || typeof parsed !== "object") return null;
    const overview = (parsed as { overview?: unknown }).overview;
    if (!overview || typeof overview !== "object" || Array.isArray(overview)) return null;
    const log = (parsed as { log?: unknown }).log;
    return {
      overview: overview as Record<string, unknown>,
      log: Array.isArray(log) ? log : [],
    };
  } catch {
    return null;
  }
}

export interface EventSourceSpec {
  url: string;
  headers: Record<string, string>;
}

/** 公开流：匿名，服务端只推白名单事件。 */
export function createPublicEventSource(path: string, screenId?: string | null): EventSourceSpec {
  const url = screenId
    ? `${path}${path.includes("?") ? "&" : "?"}screen_id=${encodeURIComponent(screenId)}`
    : path;
  return { url, headers: { Accept: "text/event-stream" } };
}

/** 登录流：Bearer + 全量事件；token 在建立连接时读取。 */
export function createAuthEventSource(path: string, token: string = getToken()): EventSourceSpec {
  return {
    url: path,
    headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}` },
  };
}

interface RunnerOptions {
  /** 返回 null 表示缺少凭据，直接进入 expired。 */
  source: () => EventSourceSpec | null;
  onEvent: (event: SseEvent) => void;
  onState: (state: StreamState) => void;
  stopOnAuthFailure?: boolean;
}

/** 底层 Runner：返回 dispose。所有 hook 与手工订阅共用。 */
export function runEventStream(options: RunnerOptions): () => void {
  const { source, onEvent, onState, stopOnAuthFailure = true } = options;
  let disposed = false;
  let active: AbortController | null = null;
  let attempt = 0;
  let timer: number | undefined;
  let generation = 0;
  let live = false;

  const scheduleRetry = () => {
    if (disposed) return;
    const delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
    attempt += 1;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      if (!document.hidden) void connect();
    }, delay);
  };

  const connect = async (): Promise<void> => {
    if (disposed) return;
    if (document.hidden) {
      onState("idle");
      return;
    }
    const spec = source();
    if (!spec) {
      onState("expired");
      return;
    }
    const gen = ++generation;
    active?.abort();
    const controller = new AbortController();
    active = controller;
    if (!live) onState("connecting");

    let lastDataAt = Date.now();
    let idleAborted = false;
    const watchdog = window.setInterval(() => {
      if (Date.now() - lastDataAt < IDLE_TIMEOUT_MS) return;
      idleAborted = true;
      window.clearInterval(watchdog);
      controller.abort();
    }, WATCHDOG_TICK_MS);

    try {
      const res = await fetch(spec.url, { headers: spec.headers, signal: controller.signal });
      if (disposed || gen !== generation) return;
      if (stopOnAuthFailure && (res.status === 401 || res.status === 403)) {
        onState("expired");
        return;
      }
      if (!res.ok || !res.body) throw new Error(`sse ${res.status}`);
      attempt = 0;
      live = true;
      onState("live");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const feed = createEventFeed((event) => onEvent(event));
      for (;;) {
        const chunk = await reader.read();
        if (disposed || gen !== generation || chunk.done) break;
        lastDataAt = Date.now();
        feed(decoder.decode(chunk.value, { stream: true }));
      }
      feed(decoder.decode());
      if (disposed || gen !== generation) return;
      live = false;
      onState("lost");
      scheduleRetry();
    } catch (error) {
      if (disposed || gen !== generation) return;
      if (error instanceof DOMException && error.name === "AbortError" && !idleAborted) return;
      live = false;
      onState("lost");
      scheduleRetry();
    } finally {
      window.clearInterval(watchdog);
    }
  };

  const onVisibility = () => {
    if (document.hidden) return;
    attempt = 0;
    window.clearTimeout(timer);
    void connect();
  };

  void connect();
  document.addEventListener("visibilitychange", onVisibility);

  return () => {
    disposed = true;
    generation += 1;
    active?.abort();
    window.clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

export interface UseEventStreamOptions {
  enabled: boolean;
  path: string;
  screenId?: string | null;
  auth?: boolean;
  onEvent: (event: SseEvent) => void;
  /** 变化时重建连接（用于手动重连）。 */
  nonce?: number;
}

/** 通用订阅 hook；事件回调始终取最新闭包。 */
export function useEventStream(options: UseEventStreamOptions): StreamState {
  const { enabled, path, screenId = null, auth = false, nonce = 0 } = options;
  const callbackRef = useRef(options.onEvent);
  callbackRef.current = options.onEvent;
  const [state, setState] = useState<StreamState>("idle");

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    const dispose = runEventStream({
      source: () =>
        auth ? createAuthEventSource(path) : createPublicEventSource(path, screenId),
      onEvent: (event) => callbackRef.current(event),
      onState: setState,
    });
    return dispose;
  }, [enabled, path, screenId, auth, nonce]);

  return state;
}

/** 兼容入口：协同增量事件流（无初始快照）。 */
export function useCollabEvents(options: {
  enabled: boolean;
  url: string;
  token?: string;
  screenId?: string | null;
  onEvent: (event: SseEvent) => void;
}): StreamState {
  const { enabled, url, token, screenId = null, onEvent } = options;
  return useEventStream({
    enabled,
    path: url,
    screenId,
    auth: Boolean(token),
    onEvent,
  });
}

function signature(snapshot: StreamSnapshot): string {
  try {
    return JSON.stringify(snapshot);
  } catch {
    return String(Date.now());
  }
}

/** 登录后的实时信号：去重后的快照才触发回调；401/403 停止重连。 */
export function useStreamSignal(options: {
  enabled: boolean;
  onSnapshot: () => void;
}): { state: StreamState; reconnect: () => void } {
  const { enabled, onSnapshot } = options;
  const callbackRef = useRef(onSnapshot);
  callbackRef.current = onSnapshot;
  const lastSignature = useRef("");
  const [nonce, setNonce] = useState(0);

  const state = useEventStream({
    enabled,
    path: "/api/stream",
    auth: true,
    nonce,
    onEvent: (event) => {
      const snapshot = parseStreamPayload(event.data);
      if (!snapshot) return;
      const next = signature(snapshot);
      if (next === lastSignature.current) return;
      lastSignature.current = next;
      callbackRef.current();
    },
  });

  const reconnect = useCallback(() => {
    lastSignature.current = "";
    setNonce((value) => value + 1);
  }, []);

  return { state, reconnect };
}
