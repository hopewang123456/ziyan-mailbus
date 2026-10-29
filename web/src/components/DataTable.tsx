import type { ReactNode } from "react";

/**
 * P5 毛刺清理：ApiListPage 的 FormishView 递归键值套壳 → 正经表格列表。
 * 列定义驱动；空态/加载态统一；行点击可选。样式沿用驾驶舱 soft-* 体系。
 */

export type Col<T> = {
  key: string;
  label: string;
  /** 单元格渲染（缺省 String(row[key])，null/空 → —） */
  render?: (row: T) => ReactNode;
  /** tailwind width 类（如 w-40） */
  width?: string;
};

export function DataTable<T extends Record<string, unknown>>({
  rows,
  cols,
  empty = "暂无条目",
  loading = false,
  onRowClick,
}: {
  rows: T[] | null | undefined;
  cols: Col<T>[];
  empty?: string;
  loading?: boolean;
  onRowClick?: (row: T) => void;
}) {
  if (loading || rows == null) return <p className="text-sm text-mute">加载中…</p>;
  if (!rows.length) return <p className="text-sm text-mute">{empty}</p>;

  const cell = (row: T, c: Col<T>): ReactNode =>
    c.render ? c.render(row) : fmt(row[c.key]);

  return (
    <div className="overflow-x-auto">
      <table className="hud-table w-full border-collapse text-left">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={`hud-table-th ${c.width ?? ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={String(row.id ?? row.task_id ?? row.intake_id ?? i)}
              className={onRowClick ? "cursor-pointer hud-table-row" : "hud-table-row"}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {cols.map((c) => (
                <td key={c.key} className="hud-table-td font-mono text-xs">
                  {cell(row, c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function fmt(v: unknown): string {
  if (v == null || v === "") return "—";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

/** 轻状态徽标（succeeded/failed/pending… → 色点+词）。 */
export function StateChip({ state }: { state: unknown }) {
  const s = String(state ?? "");
  const tone = /succ|pass|approved|ok|done/i.test(s)
    ? "bg-emerald-400"
    : /fail|deny|error|crit/i.test(s)
      ? "bg-rose-400"
      : /pending|queued|await/i.test(s)
        ? "bg-amber-300"
        : /cancel/i.test(s)
          ? "bg-zinc-400"
          : "bg-sky-300";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${tone}`} />
      {s || "—"}
    </span>
  );
}

/** 时间列：截到分钟（created_at/updated_at 通常是 ISO）。 */
export function shortTime(v: unknown): string {
  const s = String(v ?? "");
  if (!s) return "—";
  return s.length > 16 ? s.slice(0, 16).replace("T", " ") : s;
}
