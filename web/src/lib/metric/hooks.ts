import { useEffect, useRef, useState } from "react";
import {
  metricOverview as apiOverview,
  metricTrend as apiTrend,
  metricBreakdown as apiBreakdown,
  metricManifest as apiManifest,
  listMetricRules as apiListRules,
} from "./api";
import type { ApiResult } from "../api";
import type {
  MetricOverviewOut,
  MetricTrendOut,
  MetricBreakdownOut,
  MetricManifestOut,
} from "./view";

/**
 * Metric 域 hooks。
 */

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

export function useMetricOverview(query?: { from?: string | null; to?: string | null }) {
  return useSingle<MetricOverviewOut>(
    () => apiOverview({ from: query?.from, to: query?.to }),
    [query?.from, query?.to],
  );
}

export function useTrend(query: { metric?: string[] | null; from?: string | null; to?: string | null; bucket?: string }) {
  return useSingle<MetricTrendOut>(
    () => apiTrend(query),
    [query.metric?.join(","), query.from, query.to, query.bucket],
  );
}

export function useBreakdown(query: { metric?: string | null; from?: string | null; to?: string | null }) {
  return useSingle<MetricBreakdownOut>(
    () => apiBreakdown(query),
    [query.metric, query.from, query.to],
  );
}

export function useManifest() {
  return useSingle<MetricManifestOut>(() => apiManifest(), []);
}

export function useMetricRules(query?: { limit?: number; offset?: number }) {
  return useList<any, any>(
    () => apiListRules({ limit: query?.limit ?? 100, offset: query?.offset ?? 0 }),
    [query?.limit, query?.offset],
  );
}
