import type { ReactNode } from "react";

/** 管理中心设计系统（P3）— 表格 / 页头 / 标签 / 区块容器 */

export type TableColumn<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
};

export function ConsoleTable<T>({
  columns,
  rows,
  rowKey,
  empty = "暂无数据",
  loading,
  onRowClick,
  selectedKey,
}: {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string;
  empty?: string;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  selectedKey?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-rail">
      <table className="w-full min-w-[560px] border-collapse text-left">
        <thead>
          <tr className="border-b border-rail bg-hull/60">
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2.5 text-[11px] font-medium uppercase tracking-wider text-mute ${c.className || ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-xs text-mute">
                加载中…
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-xs text-mute">
                {empty}
              </td>
            </tr>
          )}
          {!loading &&
            rows.map((row, i) => {
              const rk = rowKey(row, i);
              const selected = selectedKey !== undefined && rk === selectedKey;
              return (
                <tr
                  key={rk}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={`border-b border-rail/50 last:border-0 ${
                    onRowClick ? "cursor-pointer hover:bg-rail/20" : ""
                  } ${selected ? "bg-rail/40" : ""}`}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={`px-3 py-2.5 text-xs text-frost/90 ${c.className || ""}`}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
        </tbody>
      </table>
    </div>
  );
}

export function ConsolePageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-xl tracking-tight text-frost">{title}</h1>
        {description && <p className="mt-1 text-xs text-mute">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function ConsoleTag({ tone = "default", children }: { tone?: "default" | "ok" | "warn" | "danger"; children: ReactNode }) {
  const tones: Record<string, string> = {
    default: "border-rail text-mute",
    ok: "border-mint/50 text-mint",
    warn: "border-amber-signal/50 text-amber-signal",
    danger: "border-flare/50 text-flare",
  };
  return <span className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] ${tones[tone]}`}>{children}</span>;
}

export function ConsoleSection({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="mb-6">
      <div className="mb-2.5 flex items-center justify-between">
        <h2 className="text-sm font-medium text-frost/90">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
