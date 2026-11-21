import { useEffect, useState } from "react";
import { api, getToken } from "./api";

export type ConsoleAccessState =
  | "loading"
  | "setup"
  | "unauthenticated"
  | "unavailable"
  | "denied"
  | "allowed";

export interface ConsoleAccess {
  state: ConsoleAccessState;
  /** 超级管理员（capabilities 含 "*"）：可进设置向导、开关端点与管理者。 */
  superAdmin: boolean;
  capabilities: string[];
  employeeId?: string;
  retry: () => void;
}

type AccessState = Omit<ConsoleAccess, "retry">;
type BootstrapStatus = { steps?: Array<{ step: string; done: boolean }> };

/** 直连失败为 0；开发代理在上游断连时可能返回 5xx。 */
export function isServiceUnavailable(status: number): boolean {
  return status === 0 || status >= 500;
}

const state = (
  value: ConsoleAccessState,
  capabilities: string[] = [],
  employeeId?: string,
): AccessState => ({
  state: value,
  superAdmin: capabilities.includes("*"),
  capabilities,
  employeeId,
});

/** 管理端可见性：首装、未登录、无权限和服务不可用分别呈现。 */
export function useConsoleAccess(): ConsoleAccess {
  const [access, setAccess] = useState<AccessState>(state("loading"));
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let alive = true;
    let sequence = 0;
    const check = async () => {
      const current = ++sequence;
      setAccess(state("loading"));
      if (!getToken()) {
        const bootstrap = await api<BootstrapStatus>("/api/identity/bootstrap");
        if (!alive || current !== sequence) return;
        if (!bootstrap.ok) {
          setAccess(state(isServiceUnavailable(bootstrap.status) ? "unavailable" : "unauthenticated"));
          return;
        }
        const superAdminDone = bootstrap.data.steps?.some(
          (step) => step.step === "super_admin" && step.done,
        );
        setAccess(state(superAdminDone ? "unauthenticated" : "setup"));
        return;
      }

      const result = await api<{ employee_id?: string; capabilities?: string[] }>("/api/identity/me");
      if (!alive || current !== sequence) return;
      if (!result.ok) {
        const next = isServiceUnavailable(result.status)
          ? "unavailable"
          : result.status === 401
            ? "unauthenticated"
            : "denied";
        setAccess(state(next));
        return;
      }
      const capabilities = result.data.capabilities ?? [];
      const allowed = capabilities.includes("*") || capabilities.includes("console_admin");
      setAccess(state(allowed ? "allowed" : "denied", capabilities, result.data.employee_id));
    };
    void check();
    const onAuthChange = () => void check();
    window.addEventListener("mailbus:auth-ok", onAuthChange);
    window.addEventListener("mailbus:auth-required", onAuthChange);
    return () => {
      alive = false;
      window.removeEventListener("mailbus:auth-ok", onAuthChange);
      window.removeEventListener("mailbus:auth-required", onAuthChange);
    };
  }, [revision]);

  return { ...access, retry: () => setRevision((value) => value + 1) };
}

/** 保持当前登录员工在线：每 60 秒上报心跳；大屏常驻时同样需要。 */
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
