import { useEffect, useRef, useState } from "react";
import {
  listTasks as apiListTasks,
  getTask as apiGetTask,
  summary as apiSummary,
  getTaskTrace as apiGetTaskTrace,
  listApprovals as apiListApprovals,
  getApproval as apiGetApproval,
  type ListTasksQuery,
  type ListApprovalsQuery,
} from "./api";
import {
  mapTaskSummary,
  mapTaskDetail,
  mapTraceEvent,
  mapSummary,
  mapApproval,
} from "./view";
import type {
  TaskDetailRow,
  TraceEventRow,
  SummaryRow,
  ApprovalRow,
} from "./view";
import type { ApiResult } from "../api";

/**
 * 任务域 hooks：统一 AbortController、竞态丢弃、刷新。
 * 与 workflow/hooks.ts 风格一致。
 */

function usePaginated<T, R>(
  fetcher: () => Promise<ApiResult<{ items: R[]; total: number; limit: number; offset: number }>>,
  mapper: (item: R) => T,
  deps: readonly unknown[],
  enabled = true,
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setItems([]);
      setTotal(0);
      setLoading(false);
      setError(null);
      return;
    }
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
        setLimit(d.limit ?? 100);
        setOffset(d.offset ?? 0);
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, enabled, ...deps]);

  const refresh = () => setRev((v) => v + 1);
  return { items, total, limit, offset, loading, error, refresh };
}

export function useTasks(query: ListTasksQuery = {}, enabled = true) {
  return usePaginated(
    () => apiListTasks(query),
    mapTaskSummary,
    [query.state, query.owner_id, query.workflow_id, query.limit, query.offset],
    enabled,
  );
}

export function useApprovals(query: ListApprovalsQuery = {}, enabled = true) {
  return usePaginated(
    () => apiListApprovals(query),
    mapApproval,
    [query.state, query.limit, query.offset],
    enabled,
  );
}

export function useTask(taskId: string | null) {
  const [data, setData] = useState<TaskDetailRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    if (!taskId) { setData(null); setError(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetTask(taskId).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) setData(mapTaskDetail(result.data));
      else setError(result.error ?? "加载失败");
    });
    return () => controller.abort();
  }, [taskId, rev]);

  const refresh = () => setRev((v) => v + 1);
  return { data, loading, error, refresh };
}

export function useApproval(approvalId: string | null) {
  const [data, setData] = useState<ApprovalRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    if (!approvalId) {
      setData(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetApproval(approvalId).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) setData(mapApproval(result.data));
      else setError(result.error ?? "加载失败");
    });
    return () => controller.abort();
  }, [approvalId, rev]);

  const refresh = () => setRev((v) => v + 1);
  return { data, loading, error, refresh };
}

export function useTaskTrace(taskId: string | null) {
  const [events, setEvents] = useState<TraceEventRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    if (!taskId) { setEvents([]); setError(null); return; }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetTaskTrace(taskId).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) {
        const rows = (result.data.events ?? []).map(mapTraceEvent);
        // 按时间升序；缺失时间的放到末尾
        rows.sort((a, b) => {
          if (!a.at && !b.at) return 0;
          if (!a.at) return 1;
          if (!b.at) return -1;
          return new Date(a.at).getTime() - new Date(b.at).getTime();
        });
        setEvents(rows);
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
  }, [taskId, rev]);

  const refresh = () => setRev((v) => v + 1);
  return { events, loading, error, refresh };
}

export function useSummary() {
  const [data, setData] = useState<SummaryRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiSummary().then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) setData(mapSummary(result.data));
      else setError(result.error ?? "加载失败");
    });
    return () => controller.abort();
  }, [rev]);

  const refresh = () => setRev((v) => v + 1);
  return { data, loading, error, refresh };
}
