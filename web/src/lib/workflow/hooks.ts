import { useEffect, useRef, useState } from "react";
import {
  listWorkflows as apiListWorkflows,
  getWorkflow as apiGetWorkflow,
  listVersions as apiListVersions,
  getGraph as apiGetGraph,
} from "./api";
import { mapWorkflow, mapVersion, mapGraph } from "./view";
import type { WorkflowRow, GraphRow } from "./view";
import type { ApiResult } from "../api";

/**
 * 工作流域 hooks：统一 AbortController、竞态丢弃、刷新。
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

export function useWorkflows(options: { limit?: number; offset?: number } = {}) {
  return usePaginated(
    () => apiListWorkflows({ limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapWorkflow,
    [options.limit, options.offset],
  );
}

export function useWorkflow(workflowId: string | null) {
  const [data, setData] = useState<WorkflowRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workflowId) { setData(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetWorkflow(workflowId).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) setData(mapWorkflow(result.data));
      else setError(result.error ?? "加载失败");
    });
    return () => controller.abort();
  }, [workflowId]);

  return { data, loading, error };
}

export function useVersions(workflowId: string | null) {
  return usePaginated(
    () => apiListVersions(workflowId!),
    mapVersion,
    [workflowId],
  );
}

export function useGraph(workflowId: string | null, version: number | null) {
  const [data, setData] = useState<GraphRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workflowId || version === null) { setData(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetGraph(workflowId, version).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) setData(mapGraph(result.data));
      else setError(result.error ?? "加载失败");
    });
    return () => controller.abort();
  }, [workflowId, version]);

  return { data, loading, error };
}
