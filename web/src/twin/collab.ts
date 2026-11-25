import { useCallback, useEffect, useRef, useState } from "react";
import { useEventStream } from "../lib/events";

/**
 * 多端同步：BroadcastChannel 广播「聚焦楼层 / 选中员工」。
 * 跨设备聚焦由 `lib/events.ts` 的公开流统一处理，这里不再重复登记/订阅。
 */

export interface RemoteView {
  floorId: string | null;
  seatId: string | null;
}

/** 管理端协同 SSE：Bearer 读 /api/collab/stream；接口不存在时静默。 */
export function useCollabStream(
  enabled: boolean,
  onEvent: (event: string, data: unknown) => void,
): boolean {
  const callbackRef = useRef(onEvent);
  callbackRef.current = onEvent;

  const state = useEventStream({
    enabled,
    path: "/api/collab/stream",
    auth: true,
    onEvent: (event) => {
      try {
        callbackRef.current(event.event, JSON.parse(event.data));
      } catch {
        // 坏帧直接跳过
      }
    },
  });

  return state === "live";
}

export function useScreenSync(onRemote: (view: RemoteView) => void) {
  const [peers, setPeers] = useState(0);
  const idRef = useRef(`screen-${Math.random().toString(36).slice(2, 8)}`);
  const channelRef = useRef<BroadcastChannel | null>(null);
  const peersRef = useRef<Map<string, number>>(new Map());
  const viewRef = useRef<RemoteView>({ floorId: null, seatId: null });
  const onRemoteRef = useRef(onRemote);
  onRemoteRef.current = onRemote;

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel("ziyan-twin-sync");
    channelRef.current = channel;

    const beat = () => {
      channel.postMessage({ t: "beat", id: idRef.current, at: Date.now() });
      const now = Date.now();
      for (const [id, ts] of peersRef.current) {
        if (now - ts > 12_000) peersRef.current.delete(id);
      }
      setPeers(peersRef.current.size);
    };

    channel.onmessage = (event) => {
      const data = event.data as { t?: string; id?: string; at?: number; view?: RemoteView };
      if (!data?.t || !data.id || data.id === idRef.current) return;
      if (data.t === "beat" || data.t === "hello") {
        peersRef.current.set(data.id, Date.now());
        setPeers(peersRef.current.size);
        if (data.t === "hello") {
          channel.postMessage({ t: "beat", id: idRef.current, at: Date.now() });
        }
      }
      if (data.t === "view" && data.view && data.at && Date.now() - data.at < 4000) {
        onRemoteRef.current(data.view);
      }
    };

    channel.postMessage({ t: "hello", id: idRef.current, at: Date.now() });
    const timer = window.setInterval(beat, 4000);

    return () => {
      window.clearInterval(timer);
      channel.close();
      channelRef.current = null;
    };
  }, []);

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
