import { useEffect, useRef, useState } from "react";
import { listAgents as apiListAgents, listAgentInvites as apiListAgentInvites } from "./api";
import { mapAgent, mapAgentInvite } from "./view";
import type { AgentRow, AgentInviteRow } from "./view";
import type { ApiResult } from "../api";

/**
 * Agent 域 hooks。
 */

function usePaginated<T, R>(
  fetcher: () => Promise<ApiResult<{ items: R[]; total: number }>>,
  mapper: (item: R) => T,
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
        setItems((d.items ?? []).map(mapper));
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

export function useAgents(options: { enabled?: boolean | null; limit?: number; offset?: number } = {}) {
  return usePaginated<AgentRow, any>(
    () => apiListAgents({ enabled: options.enabled, limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapAgent,
    [options.enabled, options.limit, options.offset],
  );
}

export function useAgentInvites(options: { limit?: number; offset?: number } = {}) {
  return usePaginated<AgentInviteRow, any>(
    () => apiListAgentInvites({ limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapAgentInvite,
    [options.limit, options.offset],
  );
}
