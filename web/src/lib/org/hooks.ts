import { useEffect, useRef, useState } from "react";
import {
  listEmployees as apiListEmployees,
  getEmployee as apiGetEmployee,
  listPositions as apiListPositions,
  listRoles as apiListRoles,
  listTeams as apiListTeams,
} from "./api";
import { mapEmployee, mapPosition, mapRole, mapTeam } from "./view";
import type { EmployeeRow, PositionRow, RoleRow, TeamRow } from "./view";
import type { ApiResult } from "../api";

/**
 * 组织域 hooks：统一 AbortController、竞态丢弃、刷新。
 * 页面组件只从 hooks.ts 拿数据，不直接调用 api.ts。
 */

export interface PageResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListOptions {
  limit?: number;
  offset?: number;
  enabled?: boolean;
}

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

// === 员工 ===

export function useEmployees(options: { type?: "human" | "agent" | null; limit?: number; offset?: number } = {}) {
  return usePaginated<EmployeeRow, any>(
    () => apiListEmployees({
      type: options.type ?? null,
      limit: options.limit ?? 100,
      offset: options.offset ?? 0,
    }),
    mapEmployee,
    [options.type, options.limit, options.offset],
  );
}

export function useEmployee(employeeId: string | null) {
  const [data, setData] = useState<EmployeeRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!employeeId) {
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiGetEmployee(employeeId).then((result) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      if (result.ok) {
        setData(mapEmployee(result.data));
      } else {
        setError(result.error ?? "加载失败");
      }
    });
    return () => controller.abort();
  }, [employeeId]);

  return { data, loading, error, refresh: () => { /* 简化版 */ } };
}

// === 岗位 ===

export function usePositions(options: { limit?: number; offset?: number } = {}) {
  return usePaginated<PositionRow, any>(
    () => apiListPositions({ limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapPosition,
    [options.limit, options.offset],
  );
}

// === 角色 ===

export function useRoles(options: { limit?: number; offset?: number } = {}) {
  return usePaginated<RoleRow, any>(
    () => apiListRoles({ limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapRole,
    [options.limit, options.offset],
  );
}

// === 团队 ===

export function useTeams(options: { limit?: number; offset?: number } = {}) {
  return usePaginated<TeamRow, any>(
    () => apiListTeams({ limit: options.limit ?? 100, offset: options.offset ?? 0 }),
    mapTeam,
    [options.limit, options.offset],
  );
}
