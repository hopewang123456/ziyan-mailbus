import { useEffect, useRef, useState } from "react";
import { listMessages as apiListMessages, getMessage as apiGetMessage, traceMessage as apiTraceMessage } from "./api";
import type { ApiResult } from "../api";
import { useEventStream } from "../events";
import type { MessageOut, MessageTraceOut } from "./view";

/**
 * Message 域 hooks。
 */

function useList<T, R>(
  fetcher: () => Promise<ApiResult<{ items: R[]; total: number }>>,
  deps: readonly unknown[],
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    const current = ++seq.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    void fetcher().then((result) => {
      if (current !== seq.current || controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) {
        const d = result.data;
        setItems((d.items ?? []) as unknown as T[]);
        setTotal(d.total ?? 0);
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
  }, [rev, ...deps]);

  const refresh = () => setRev((v) => v + 1);

  return { items, total, loading, error, refresh };
}

function useSingle<T>(
  fetcher: () => Promise<ApiResult<T>>,
  deps: readonly unknown[],
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    const current = ++seq.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    void fetcher().then((result) => {
      if (current !== seq.current || controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) {
        setData(result.data);
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
  }, [rev, ...deps]);

  const refresh = () => setRev((v) => v + 1);

  return { data, loading, error, refresh };
}

export function useMessages(options: {
  employee_id?: string | null;
  channel?: "file_bus" | "a2a" | "mcp" | null;
  kind?: string | null;
  limit?: number;
  offset?: number;
} = {}) {
  return useList<MessageOut, MessageOut>(
    () =>
      apiListMessages({
        employee_id: options.employee_id,
        channel: options.channel,
        kind: options.kind,
        limit: options.limit ?? 100,
        offset: options.offset ?? 0,
      }),
    [options.employee_id, options.channel, options.kind, options.limit, options.offset],
  );
}

export function useMessage(messageId: string | null) {
  return useSingle<MessageOut>(
    () => apiGetMessage(messageId as string),
    [messageId],
  );
}

export function useTrace(messageId: string | null) {
  return useSingle<MessageTraceOut>(
    () => apiTraceMessage(messageId as string),
    [messageId],
  );
}

/** 登录 SSE 收到 message.created 后刷新当前筛选结果。 */
export function useLiveMessages(options: {
  employee_id?: string | null;
  channel?: "file_bus" | "a2a" | "mcp" | null;
  kind?: string | null;
  limit?: number;
  offset?: number;
} = {}) {
  const base = useMessages(options);
  const streamState = useEventStream({
    enabled: true,
    path: "/api/stream",
    auth: true,
    onEvent: (event) => {
      if (event.event === "message.created") base.refresh();
    },
  });

  return { ...base, streamState };
}
