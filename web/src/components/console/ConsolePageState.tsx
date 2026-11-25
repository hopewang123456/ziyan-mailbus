import type { ReactNode } from "react";

/**
 * 统一页面状态：加载骨架、空态、错误、403、404、服务不可用。
 * 页面不再各自拼空态/错误样式。
 */

export type PageStateKind =
  | "loading"
  | "empty"
  | "error"
  | "forbidden"
  | "not-found"
  | "unavailable";

const DEFAULTS: Record<PageStateKind, { title: string; description: string }> = {
  loading: { title: "加载中…", description: "正在获取数据" },
  empty: { title: "暂无数据", description: "当前筛选条件下没有记录" },
  error: { title: "加载失败", description: "请稍后重试" },
  forbidden: { title: "无权访问", description: "当前账号没有该页面的权限" },
  "not-found": { title: "资源不存在", description: "记录可能已被删除或地址有误" },
  unavailable: { title: "服务不可用", description: "无法连接后端服务，请稍后重试" },
};

export function ConsoleSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" className="space-y-2">
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="h-9 animate-pulse rounded border border-rail/60 bg-hull/60"
        />
      ))}
    </div>
  );
}

export function ConsolePageState({
  kind,
  title,
  description,
  action,
}: {
  kind: PageStateKind;
  title?: string;
  description?: string;
  action?: ReactNode;
}) {
  if (kind === "loading") return <ConsoleSkeleton />;
  const fallback = DEFAULTS[kind];
  return (
    <div
      role={kind === "error" || kind === "unavailable" ? "alert" : "status"}
      className="flex min-h-[220px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-rail px-6 py-10 text-center"
    >
      <p className="font-display text-sm text-frost">{title ?? fallback.title}</p>
      <p className="max-w-sm text-xs text-mute">{description ?? fallback.description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
