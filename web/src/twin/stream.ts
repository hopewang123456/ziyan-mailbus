import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../lib/api";

/** 实时快照：后端 /api/stream 只推送 { overview, log }，不含布局。 */
export interface StreamSnapshot {
  overview: Record<string, unknown>;
  log: unknown[];
}

export type StreamState = "idle" | "connecting" | "live" | "lost" | "expired";

const RETRY_MS = [1000, 2000, 4000, 8000, 15000];
/** 后端每 15 秒发一次心跳；连续 40 秒没有任何数据即判定连接半开，主动断开重连。 */
const IDLE_TIMEOUT_MS = 40_000;
const WATCHDOG_TICK_MS = 5_000;

/**
 * SSE 分帧解析：按空行切帧，忽略 `: heartbeat` 注释行，
 * 多行 data 用换行拼接后回调。返回的 feed 可重复投喂任意切片。
 */
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
    // 单帧上限保护：坏数据不允许无限占用内存
    if (buffer.length > 1_000_000) buffer = "";
  };
}

export interface CollabEvent {
  event: string;
  data: string;
}

/**
 * 协同 SSE 分帧：保留 `event:` 名称，忽略 `: ping`，
 * 与 overview 流共用空行分帧规则。
 */
export function createEventFeed(onEvent: (event: CollabEvent) => void) {
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

/** 协同增量事件流：无初始快照，只消费 event + data。 */
export function useCollabEvents(options: {
  enabled: boolean;
  url: string;
  token?: string;
  onEvent: (event: CollabEvent) => void;
}): StreamState {
  const { enabled, url, token } = options;
  const callbackRef = useRef(options.onEvent);
  callbackRef.current = options.onEvent;
  const [state, setState] = useState<StreamState>("idle");

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    let active: AbortController | null = null;
    let disposed = false;
    let attempt = 0;
    let timer: number | undefined;

    const connect = async () => {
      if (disposed) return;
      if (document.hidden) {
        setState("idle");
        return;
      }
      setState((prev) => (prev === "live" ? prev : "connecting"));
      const controller = new AbortController();
      active = controller;
      let lastDataAt = Date.now();
      let idleAborted = false;
      const watchdog = window.setInterval(() => {
        if (Date.now() - lastDataAt < IDLE_TIMEOUT_MS) return;
        idleAborted = true;
        window.clearInterval(watchdog);
        controller.abort();
      }, WATCHDOG_TICK_MS);
      try {
        const headers: Record<string, string> = { Accept: "text/event-stream" };
        if (token) headers.Authorization = `Bearer ${token}`;
        const res = await fetch(url, { headers, signal: controller.signal });
        if (disposed) return;
        if (token && (res.status === 401 || res.status === 403)) {
          setState("expired");
          return;
        }
        if (!res.ok || !res.body) throw new Error(`collab stream ${res.status}`);
        attempt = 0;
        setState("live");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const feed = createEventFeed((event) => callbackRef.current(event));
        for (;;) {
          const chunk = await reader.read();
          if (disposed || chunk.done) break;
          lastDataAt = Date.now();
          feed(decoder.decode(chunk.value, { stream: true }));
        }
        feed(decoder.decode());
        if (disposed) return;
        setState("lost");
        scheduleRetry();
      } catch (error) {
        if (disposed) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          if (!idleAborted) return;
        }
        setState("lost");
        scheduleRetry();
      } finally {
        window.clearInterval(watchdog);
      }
    };

    const scheduleRetry = () => {
      if (disposed) return;
      const delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
      attempt += 1;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (!document.hidden) void connect();
      }, delay);
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
      active?.abort();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, url, token]);

  return state;
}

/** 解析一条 data 负载；结构不符或坏 JSON 返回 null。 */
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

function signature(snapshot: StreamSnapshot): string {
  try {
    return JSON.stringify(snapshot);
  } catch {
    return String(Date.now());
  }
}

/**
 * 登录后的实时信号：fetch + Bearer 读取 SSE，只把去重后的有效快照
 * 交给调用方；心跳与坏帧不触发回调。401/403 停止重连，网络错误受控退避。
 */
export function useStreamSignal(options: {
  enabled: boolean;
  onSnapshot: () => void;
}): { state: StreamState; reconnect: () => void } {
  const { enabled, onSnapshot } = options;
  const callbackRef = useRef(onSnapshot);
  callbackRef.current = onSnapshot;
  const [state, setState] = useState<StreamState>("idle");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    const token = getToken();
    if (!token) {
      setState("expired");
      return;
    }

    let active: AbortController | null = null;
    let disposed = false;
    let attempt = 0;
    let timer: number | undefined;
    let lastSignature = "";

    const connect = async () => {
      if (disposed) return;
      if (document.hidden) {
        setState("idle");
        return;
      }
      setState((prev) => (prev === "live" ? prev : "connecting"));
      const controller = new AbortController();
      active = controller;
      let lastDataAt = Date.now();
      let idleAborted = false;
      const watchdog = window.setInterval(() => {
        if (Date.now() - lastDataAt < IDLE_TIMEOUT_MS) return;
        idleAborted = true;
        window.clearInterval(watchdog);
        controller.abort();
      }, WATCHDOG_TICK_MS);
      try {
        const res = await fetch("/api/stream", {
          headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (disposed) return;
        if (res.status === 401 || res.status === 403) {
          setState("expired");
          return;
        }
        if (!res.ok || !res.body) {
          throw new Error(`stream ${res.status}`);
        }
        attempt = 0;
        setState("live");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const feed = createSseFeed((data) => {
          const snapshot = parseStreamPayload(data);
          if (!snapshot) return;
          const next = signature(snapshot);
          if (next === lastSignature) return;
          lastSignature = next;
          callbackRef.current();
        });
        for (;;) {
          const chunk = await reader.read();
          if (disposed || chunk.done) break;
          lastDataAt = Date.now();
          feed(decoder.decode(chunk.value, { stream: true }));
        }
        feed(decoder.decode());
        if (disposed) return;
        setState("lost");
        scheduleRetry();
      } catch (error) {
        if (disposed) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          if (!idleAborted) return;
        }
        setState("lost");
        scheduleRetry();
      } finally {
        window.clearInterval(watchdog);
      }
    };

    const scheduleRetry = () => {
      if (disposed) return;
      const delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
      attempt += 1;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (document.hidden) return;
        void connect();
      }, delay);
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
      active?.abort();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, revision]);

  const reconnect = useCallback(() => setRevision((value) => value + 1), []);
  return { state, reconnect };
}
