import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../lib/api";

export interface RemoteView {
  floorId: string | null;
  seatId: string | null;
}

/** 解析 SSE 帧：event 名 + 多行 data 合并。 */
function parseFrame(frame: string): { event: string; data: string } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

/** 公开流断线或被限流（503）后的退避重连间隔，最后一项为上限。 */
const PUBLIC_STREAM_RETRY_MS = [2000, 4000, 8000, 15000];

/**
 * 管理端协同 SSE：fetch + Bearer 读 /api/collab/stream。
 * 接口不存在时静默失败，页面继续用轮询。
 */
export function useCollabStream(
  enabled: boolean,
  onEvent: (event: string, data: unknown) => void,
): boolean {
  const callbackRef = useRef(onEvent);
  callbackRef.current = onEvent;
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const token = getToken();
    const controller = new AbortController();
    let disposed = false;

    const connect = async () => {
      try {
        const res = await fetch("/api/collab/stream", {
          headers: {
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          signal: controller.signal,
        });
        if (disposed || !res.ok || !res.body) return;
        setLive(true);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const chunk = await reader.read();
          if (disposed || chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          let cut = buffer.search(/\r?\n\r?\n/);
          while (cut >= 0) {
            const frame = buffer.slice(0, cut);
            buffer = buffer.slice(cut + (buffer.startsWith("\r\n\r\n", cut) ? 4 : 2));
            const parsed = parseFrame(frame);
            if (parsed) {
              try {
                callbackRef.current(parsed.event, JSON.parse(parsed.data));
              } catch {
                // 坏帧直接跳过
              }
            }
            cut = buffer.search(/\r?\n\r?\n/);
          }
          if (buffer.length > 1_000_000) buffer = "";
        }
      } catch {
        // 接口缺失 / 网络中断：保持轮询
      } finally {
        if (!disposed) setLive(false);
      }
    };

    void connect();
    return () => {
      disposed = true;
      controller.abort();
      setLive(false);
    };
  }, [enabled]);

  return live;
}

/**
 * 多端同步：BroadcastChannel 广播「聚焦楼层 / 选中员工」，
 * 并可选向 /api/public/collab/* 登记大屏、上报心跳、接收 screen.focus。
 */
export function useScreenSync(
  onRemote: (view: RemoteView) => void,
  options: { register?: boolean } = {},
) {
  const [peers, setPeers] = useState(0);
  const idRef = useRef(`screen-${Math.random().toString(36).slice(2, 8)}`);
  const channelRef = useRef<BroadcastChannel | null>(null);
  const peersRef = useRef<Map<string, number>>(new Map());
  const viewRef = useRef<RemoteView>({ floorId: null, seatId: null });
  const onRemoteRef = useRef(onRemote);
  onRemoteRef.current = onRemote;
  const register = options.register !== false;

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel("ziyan-twin-sync");
    channelRef.current = ch;
    const beat = () => {
      ch.postMessage({ t: "beat", id: idRef.current, at: Date.now() });
      const now = Date.now();
      for (const [id, ts] of peersRef.current) {
        if (now - ts > 12_000) peersRef.current.delete(id);
      }
      setPeers(peersRef.current.size);
    };
    ch.onmessage = (e) => {
      const d = e.data as { t?: string; id?: string; at?: number; view?: RemoteView };
      if (!d?.t || !d.id || d.id === idRef.current) return;
      if (d.t === "beat" || d.t === "hello") {
        peersRef.current.set(d.id, Date.now());
        setPeers(peersRef.current.size);
        if (d.t === "hello") ch.postMessage({ t: "beat", id: idRef.current, at: Date.now() });
      }
      if (d.t === "view" && d.view && d.at && Date.now() - d.at < 4000) {
        onRemoteRef.current(d.view);
      }
    };
    ch.postMessage({ t: "hello", id: idRef.current, at: Date.now() });
    const timer = window.setInterval(beat, 4000);

    // 跨设备：公开登记 + 心跳 + 只接收本屏的 screen.focus
    let disposed = false;
    let sse: AbortController | null = null;
    let heartbeat = 0;
    let retryTimer = 0;
    let attempt = 0;
    const screenId = idRef.current;
    const base = "/api/public/collab";

    const consumeFocus = (frame: string) => {
      const parsed = parseFrame(frame);
      if (parsed?.event !== "screen.focus") return;
      try {
        const data = JSON.parse(parsed.data) as {
          screen_id?: string;
          floor_id?: string | null;
          seat_id?: string | null;
        };
        // 多屏时只接受发给自己的遥控；无 screen_id 的旧事件保持兼容
        if (!data.screen_id || data.screen_id === screenId) {
          onRemoteRef.current({
            floorId: data.floor_id ?? null,
            seatId: data.seat_id ?? null,
          });
        }
      } catch {
        // 忽略坏帧
      }
    };

    const scheduleReconnect = () => {
      if (disposed) return;
      const delay = PUBLIC_STREAM_RETRY_MS[Math.min(attempt, PUBLIC_STREAM_RETRY_MS.length - 1)];
      attempt += 1;
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => void connectStream(), delay);
    };

    const connectStream = async () => {
      if (disposed) return;
      window.clearTimeout(retryTimer);
      sse?.abort();
      const controller = new AbortController();
      sse = controller;
      try {
        const res = await fetch(
          `${base}/stream?screen_id=${encodeURIComponent(screenId)}`,
          { headers: { Accept: "text/event-stream" }, signal: controller.signal },
        );
        if (disposed) return;
        if (!res.ok || !res.body) {
          // 503 表示连接数已满，交由退避重试；其它错误同样重试
          scheduleReconnect();
          return;
        }
        attempt = 0;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const chunk = await reader.read();
          if (disposed || chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          let cut = buffer.search(/\r?\n\r?\n/);
          while (cut >= 0) {
            consumeFocus(buffer.slice(0, cut));
            buffer = buffer.slice(cut + (buffer.startsWith("\r\n\r\n", cut) ? 4 : 2));
            cut = buffer.search(/\r?\n\r?\n/);
          }
        }
      } catch {
        // 主动断开（卸载/重连前 abort）不再重试
        if (disposed || controller.signal.aborted) return;
      }
      scheduleReconnect();
    };

    let registered = false;
    let screenSecret: string | null = null;
    if (register) {
      const headers = { "Content-Type": "application/json" };
      void (async () => {
        try {
          const created = await fetch(`${base}/screens`, {
            method: "POST",
            headers,
            body: JSON.stringify({ screen_id: screenId, name: `大屏 ${screenId.slice(-4)}` }),
          });
          if (disposed || !created.ok) return;
          // M14：登记时获取一次性密钥，后续心跳/离线需携带
          const createdBody = await created.json().catch(() => ({}));
          screenSecret = createdBody.secret ?? null;
          registered = true;

          heartbeat = window.setInterval(() => {
            if (disposed) return;
            void fetch(`${base}/screens/${encodeURIComponent(screenId)}/heartbeat`, {
              method: "POST",
              headers,
              body: JSON.stringify({
                floor_id: viewRef.current.floorId,
                seat_id: viewRef.current.seatId,
                ...(screenSecret ? { secret: screenSecret } : {}),
              }),
            }).catch(() => undefined);
          }, 20_000);

          await connectStream();
        } catch {
          // 未接后端时静默，BroadcastChannel 仍可用
        }
      })();
    }

    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.clearInterval(heartbeat);
      window.clearTimeout(retryTimer);
      sse?.abort();
      ch.close();
      channelRef.current = null;
      if (register && registered) {
        void fetch(`${base}/screens/${encodeURIComponent(screenId)}/leave`, {
          method: "POST",
          keepalive: true,
          headers: screenSecret ? { "Content-Type": "application/json" } : undefined,
          body: screenSecret ? JSON.stringify({ secret: screenSecret }) : undefined,
        }).catch(() => undefined);
      }
    };
  }, [register]);

  const sendView = useCallback((view: RemoteView) => {
    viewRef.current = view;
    channelRef.current?.postMessage({
      t: "view",
      id: idRef.current,
      at: Date.now(),
      view,
    });
  }, []);

  return { peers, sendView };
}
