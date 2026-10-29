/**
 * 通用 SSE 订阅 hook（P5：轮询→推送，后端双栈流端点消费端落地）。
 *
 * 协议（与 python sse.py / java StreamController 一致）：
 *   event: snapshot  data: {…}   —— 载荷变化才推（差量）
 *   event: heartbeat             —— 保活（忽略）
 *   event: done                  —— 后端 300s 关流；EventSource 自动重连
 *   event: error                 —— 流错误（状态保持旧值）
 *
 * 首帧：后端差量引擎首轮必推 snapshot，无需预 fetch。
 * 兜底：EventSource 不可用（SSR/极旧浏览器）时返回 null，调用方降级轮询。
 */
import { useEffect, useRef, useState } from "react";

export function useEventStream<T = unknown>(url: string | null): T | null {
  const [data, setData] = useState<T | null>(null);
  // 组件重挂载时避免闪回 null：保留最后一份载荷
  const lastRef = useRef<T | null>(null);

  useEffect(() => {
    if (!url || typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    const es = new EventSource(url);
    const onSnapshot = (ev: MessageEvent) => {
      try {
        const parsed = JSON.parse(ev.data) as T;
        lastRef.current = parsed;
        setData(parsed);
      } catch {
        // 脏帧忽略，状态保持
      }
    };
    es.addEventListener("snapshot", onSnapshot as EventListener);
    // 后端若用默认 message 事件名，同样接住
    es.onmessage = onSnapshot as (ev: MessageEvent) => void;
    return () => {
      es.removeEventListener("snapshot", onSnapshot as EventListener);
      es.close();
    };
  }, [url]);

  return data ?? lastRef.current;
}

/** metrics 流的 snapshot 载荷形状（与 GET /api/metrics/query 同形）。 */
export interface MetricsPointsPayload {
  status?: string;
  points?: { metric: string; value: number | null; unit?: string; error?: string }[];
}
