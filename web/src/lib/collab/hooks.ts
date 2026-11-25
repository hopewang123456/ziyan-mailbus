import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult } from "../api";
import {
  listScreens as apiListScreens,
  getScreen as apiGetScreen,
  listPairs as apiListPairs,
  listMessages as apiListMessages,
  publicScreenConfig as apiPublicScreenConfig,
  publicSeatTasks as apiPublicSeatTasks,
  publicLayout as apiPublicLayout,
} from "./api";
import {
  mapScreen,
  mapPair,
  mapMessage,
  mapPublicScreenConfig,
  type ScreenRow,
  type PairRow,
  type CollabMessageRow,
  type PublicScreenConfigRow,
} from "./view";

/**
 * 协同域 hooks：统一 AbortController、竞态丢弃、刷新。
 * 页面组件只从 hooks.ts 拿数据，不直接调用 api.ts。
 */

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SingleResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

function usePaginated<
  T,
  R extends { items: unknown[]; total: number; limit: number; offset: number },
>(
  fetcher: () => Promise<ApiResult<R>>,
  mapper: (item: R["items"][number]) => T,
  deps: readonly unknown[],
): PaginatedResult<T> & { loading: boolean; error: string | null; refresh: () => void } {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
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
        setLimit(d.limit ?? 0);
        setOffset(d.offset ?? 0);
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, ...deps]);

  const refresh = useCallback(() => setRev((v) => v + 1), []);

  return { items, total, limit, offset, loading, error, refresh };
}

function useArray<
  T,
  R,
>(
  fetcher: () => Promise<ApiResult<R[]>>,
  mapper: (item: R) => T,
  deps: readonly unknown[],
) {
  const [items, setItems] = useState<T[]>([]);
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
        setItems((result.data ?? []).map(mapper));
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, ...deps]);

  const refresh = useCallback(() => setRev((v) => v + 1), []);

  return { items, loading, error, refresh };
}

function useSingle<T>(
  fetcher: () => Promise<ApiResult<T | null>>,
  deps: readonly unknown[],
): SingleResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, ...deps]);

  const refresh = useCallback(() => setRev((v) => v + 1), []);
  return { data, loading, error, refresh };
}

// === 大屏管理 ===

export function useScreens(
  query: { limit?: number; offset?: number } = {},
) {
  return usePaginated<
    ScreenRow,
    { items: unknown[]; total: number; limit: number; offset: number }
  >(
    () => apiListScreens({ limit: query.limit ?? 100, offset: query.offset ?? 0 }),
    (item) => mapScreen(item as any),
    [query.limit, query.offset],
  );
}

export function useScreen(screenId: string | null) {
  return useSingle<ScreenRow>(
    () =>
      apiGetScreen(screenId as unknown as string).then((result) => {
        if (!result.ok) return result as ApiResult<ScreenRow | null>;
        if (!result.data) return { ok: true, data: null, status: result.status };
        return { ok: true, data: mapScreen(result.data), status: result.status } as ApiResult<ScreenRow | null>;
      }),
    [screenId],
  );
}

// === 结对 ===

export function usePairs(
  query: { state?: "active" | "ended" | null; limit?: number } = {},
) {
  return useArray<PairRow, any>(
    () => apiListPairs({ state: query.state ?? null, limit: query.limit ?? 100 }),
    (item) => mapPair(item),
    [query.state, query.limit],
  );
}

// === 协同消息 ===

export function useMessages(
  query: { pair_id?: string | null; limit?: number } = {},
) {
  return useArray<CollabMessageRow, any>(
    () => apiListMessages({ pair_id: query.pair_id ?? null, limit: query.limit ?? 100 }),
    (item) => mapMessage(item),
    [query.pair_id, query.limit],
  );
}

// === 公开投影（孪生大屏） ===

export function usePublicConfig(screenId: string | null | undefined) {
  return useSingle<PublicScreenConfigRow>(
    async () => {
      if (!screenId) return { ok: true, data: null, status: 200 };
      const result = await apiPublicScreenConfig(screenId);
      if (!result.ok) return result as ApiResult<PublicScreenConfigRow | null>;
      return { ok: true, data: mapPublicScreenConfig(result.data), status: result.status } as ApiResult<PublicScreenConfigRow | null>;
    },
    [screenId],
  );
}

export function usePublicSeatTasks(seatId: string | null | undefined) {
  return useArray<any, any>(
    async () => {
      if (!seatId) return { ok: true, data: [], status: 200 } as ApiResult<any[]>;
      const result = await apiPublicSeatTasks(seatId);
      return result as ApiResult<any[]>;
    },
    (item) => item,
    [seatId],
  );
}

// === 布局编辑器辅助 ===

export function useLayout(): SingleResult<import("../contracts").components["schemas"]["PublicOfficeSiteOut"]> {
  return useSingle<import("../contracts").components["schemas"]["PublicOfficeSiteOut"]>(
    () => apiPublicLayout() as Promise<ApiResult<any>>,
    [],
  );
}
