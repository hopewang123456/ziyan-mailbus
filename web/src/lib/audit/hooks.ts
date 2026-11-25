import { useEffect, useRef, useState } from "react";
import { listAudit as apiListAudit, getAudit as apiGetAudit } from "./api";
import type { ApiResult } from "../api";
import type { AuditEntryOut } from "./view";

/**
 * Audit 域 hooks。
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

export function useAudits(options: {
  actor?: string | null;
  action?: string | null;
  resource?: string | null;
  from?: string | null;
  to?: string | null;
  limit?: number;
  offset?: number;
} = {}) {
  return useList<AuditEntryOut, AuditEntryOut>(
    () =>
      apiListAudit({
        actor: options.actor,
        action: options.action,
        resource: options.resource,
        from: options.from,
        to: options.to,
        limit: options.limit ?? 100,
        offset: options.offset ?? 0,
      }),
    [options.actor, options.action, options.resource, options.from, options.to, options.limit, options.offset],
  );
}

export function useAudit(auditId: number | null) {
  return useSingle<AuditEntryOut>(
    () => apiGetAudit(auditId as number),
    [auditId],
  );
}
