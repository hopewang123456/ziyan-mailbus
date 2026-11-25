import type { ReactNode } from "react";
import { useConsoleAccess } from "../../lib/console-access";
import type { Permission } from "../../lib/permissions";
import { ConsolePageState } from "./ConsolePageState";

/**
 * 页面级权限门禁：直接访问无权限页面时渲染统一 403，不跳回概览。
 * 权限判断只走 `console-access` 的共享快照。
 */
export function RequirePermission({
  anyOf,
  children,
}: {
  anyOf: Permission[];
  children: ReactNode;
}) {
  const access = useConsoleAccess();
  if (access.state !== "allowed") return null;
  if (anyOf.length > 0 && !access.canAny(anyOf)) {
    return <ConsolePageState kind="forbidden" />;
  }
  return <>{children}</>;
}
