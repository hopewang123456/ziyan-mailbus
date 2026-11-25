import { useEffect, useSyncExternalStore } from "react";
import { api, getToken } from "./api";
import {
  can as checkPermission,
  canAny as checkAnyPermission,
  type DataScope,
  type Permission,
} from "./permissions";

export type ConsoleAccessState =
  | "loading"
  | "setup"
  | "unauthenticated"
  | "unavailable"
  | "allowed";

export interface ConsoleAccess {
  state: ConsoleAccessState;
  /** `permissions` 含 `*` 或 `console_admin`：可进设置向导、开关端点与管理者。 */
  superAdmin: boolean;
  permissions: string[];
  dataScope: DataScope;
  employeeId?: string;
  displayName?: string;
  can: (permission: Permission) => boolean;
  canAny: (permissions: Permission[]) => boolean;
  retry: () => void;
}

type Snapshot = Omit<ConsoleAccess, "can" | "canAny" | "retry">;
type BootstrapStatus = { steps?: Array<{ step: string; done: boolean }> };

const initial: Snapshot = {
  state: "loading",
  superAdmin: false,
  permissions: [],
  dataScope: "self",
};

/** 直连失败为 0；开发代理在上游断连时可能返回 5xx。 */
export function isServiceUnavailable(status: number): boolean {
  return status === 0 || status >= 500;
}

function derive(
  value: ConsoleAccessState,
  permissions: string[] = [],
  employeeId?: string,
  displayName?: string,
  dataScope: DataScope = "self",
): Snapshot {
  return {
    state: value,
    superAdmin: permissions.includes("*") || permissions.includes("console_admin"),
    permissions,
    dataScope,
    employeeId,
    displayName,
  };
}

function parseScope(value: unknown): DataScope {
  return value === "team" || value === "global" ? value : "self";
}

// 单一身份快照：多个 useConsoleAccess() 共享同一次请求，避免每挂载一次就打 /me。
let snapshot: Snapshot = initial;
const listeners = new Set<() => void>();
let refreshInFlight: Promise<void> | null = null;
let listening = false;

function publish(next: Snapshot): void {
  snapshot = next;
  for (const listener of listeners) listener();
}

async function check(): Promise<void> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    publish(derive("loading"));
    if (!getToken()) {
      const bootstrap = await api<BootstrapStatus>("/api/identity/bootstrap");
      if (!bootstrap.ok) {
        publish(derive(isServiceUnavailable(bootstrap.status) ? "unavailable" : "unauthenticated"));
        return;
      }
      const superAdminDone = bootstrap.data.steps?.some(
        (step) => step.step === "super_admin" && step.done,
      );
      publish(derive(superAdminDone ? "unauthenticated" : "setup"));
      return;
    }

    const result = await api<{
      employee_id?: string;
      display_name?: string;
      permissions?: string[];
      data_scope?: string;
    }>("/api/identity/me");
    if (!result.ok) {
      publish(derive(isServiceUnavailable(result.status) ? "unavailable" : "unauthenticated"));
      return;
    }
    const permissions = Array.isArray(result.data.permissions) ? result.data.permissions : [];
    // 所有有效登录员工均可进入控制台；页面级权限由 can()/RequirePermission 判断。
    publish(
      derive(
        "allowed",
        permissions,
        result.data.employee_id,
        result.data.display_name,
        parseScope(result.data.data_scope),
      ),
    );
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

function ensureListening(): void {
  if (listening || typeof window === "undefined") return;
  listening = true;
  const onAuthChange = () => void check();
  window.addEventListener("mailbus:auth-ok", onAuthChange);
  window.addEventListener("mailbus:auth-required", onAuthChange);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  ensureListening();
  if (snapshot.state === "loading" && !refreshInFlight) void check();
  return () => listeners.delete(listener);
}

function getSnapshot(): Snapshot {
  return snapshot;
}

export function useConsoleAccess(): ConsoleAccess {
  const value = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    ...value,
    can: (permission) => checkPermission(value.permissions, permission),
    canAny: (permissions) => checkAnyPermission(value.permissions, permissions),
    retry: () => void check(),
  };
}

/**
 * 保持当前登录员工在线：每 60 秒上报心跳；大屏常驻时同样需要。
 * 路径仍为 Phase 1 员工心跳，等 B1.5 契约桩冻结后随 `permissions` 重命名一并切换。
 */
export function useStaffHeartbeat(employeeId?: string, enabled = true): void {
  useEffect(() => {
    if (!enabled || !getToken()) return;
    let disposed = false;
    let resolved = employeeId;

    const beat = async () => {
      if (!resolved) {
        const me = await api<{ employee_id?: string }>("/api/identity/me");
        if (disposed || !me.ok) return;
        resolved = me.data.employee_id;
        if (!resolved) return;
      }
      void api(`/api/identity/staff/${encodeURIComponent(resolved)}/heartbeat`, {
        method: "POST",
      });
    };

    void beat();
    const timer = window.setInterval(() => void beat(), 60_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [employeeId, enabled]);
}
