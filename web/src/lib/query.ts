import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult, ErrorKind } from "./api";

/**
 * 轻量请求 hook：取消、竞态丢弃、加载/错误/刷新。
 * 不引入全局缓存；跨页共享仅限身份、权限与大屏身份。
 */

export interface QueryError {
  message: string;
  status: number;
  kind: ErrorKind;
  fields?: Record<string, string>;
}

export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: QueryError | null;
  refresh: () => void;
}

export function useApiQuery<T>(
  fetcher: (signal: AbortSignal) => Promise<ApiResult<T>>,
  deps: readonly unknown[],
  options: { enabled?: boolean; initial?: T | null } = {},
): QueryState<T> {
  const { enabled = true, initial = null } = options;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const sequence = useRef(0);
  const [data, setData] = useState<T | null>(initial);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<QueryError | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const current = ++sequence.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    void fetcherRef.current(controller.signal).then((result) => {
      if (current !== sequence.current || controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) {
        setData(result.data);
        return;
      }
      setError({
        message: result.error,
        status: result.status,
        kind: result.kind,
        fields: result.fields,
      });
    });

    return () => controller.abort();
  }, [enabled, revision, ...deps]);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  return { data, loading, error, refresh };
}
