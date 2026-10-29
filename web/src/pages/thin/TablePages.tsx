import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { DataTable, StateChip, fmt, shortTime, type Col } from "../../components/DataTable";
import { ErrorAlert } from "../../components/ErrorAlert";

/**
 * P5 毛刺清理：三张 FormishView 递归套壳卡 → 正经表格
 * （intake 线索 / tasks 任务 / human-queue 待办）。列定义即领域形状。
 */

type Row = Record<string, unknown>;

/** 通用拉取壳：一次拉取（L3 弹窗按需打开，无轮询）。 */
function useFetchRow(path: string): { data: unknown; err: string } {
  const [data, setData] = useState<unknown>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setErr("");
      const r = await api(path);
      if (cancelled) return;
      if (r.ok) setData(r.data);
      else setErr(r.error);
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);
  return { data, err };
}

function rowsOf(data: unknown, listKey?: string): Row[] | null {
  if (data == null) return null;
  const list = listKey && typeof data === "object"
    ? (data as Record<string, unknown>)[listKey]
    : data;
  return Array.isArray(list) ? (list as Row[]) : null;
}

const intakeCols: Col<Row>[] = [
  { key: "intake_id", label: "ID", width: "w-36" },
  { key: "title", label: "标题", render: (r) => <span className="text-frost">{fmt(r.title ?? r.summary)}</span> },
  { key: "status", label: "状态", render: (r) => <StateChip state={r.status} /> },
  { key: "updated_at", label: "更新", render: (r) => shortTime(r.updated_at ?? r.created_at), width: "w-32" },
];

const taskCols: Col<Row>[] = [
  { key: "task_id", label: "任务", width: "w-40" },
  {
    key: "intent",
    label: "意图",
    render: (r) => (
      <span className="text-frost" title={fmt(r.intent)}>
        {fmt(r.intent).length > 42 ? `${fmt(r.intent).slice(0, 42)}…` : fmt(r.intent)}
      </span>
    ),
  },
  { key: "status", label: "状态", render: (r) => <StateChip state={r.status} />, width: "w-24" },
  { key: "tier", label: "级", width: "w-12" },
  { key: "updated_at", label: "更新", render: (r) => shortTime(r.updated_at), width: "w-32" },
];

const hqCols: Col<Row>[] = [
  { key: "id", label: "待办", width: "w-32" },
  { key: "type", label: "类型", width: "w-32", render: (r) => <StateChip state={r.type} /> },
  {
    key: "title",
    label: "事项",
    render: (r) => <span className="text-frost" title={fmt(r.title ?? r.prompt)}>
      {fmt(r.title ?? r.prompt).length > 46 ? `${fmt(r.title ?? r.prompt).slice(0, 46)}…` : fmt(r.title ?? r.prompt)}
    </span>,
  },
  { key: "task_id", label: "任务", width: "w-36" },
  { key: "created_at", label: "创建", render: (r) => shortTime(r.created_at), width: "w-32" },
];

export function IntakeTablePage() {
  const { data, err } = useFetchRow("/api/intake");
  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="soft-panel-title">商前线索</p>
        <p className="soft-panel-sub font-mono text-[11px]">/api/intake</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      <DataTable rows={rowsOf(data, "intakes")} cols={intakeCols} empty="暂无线索" />
    </div>
  );
}

export function TaskTablePage() {
  const { data, err } = useFetchRow("/api/tasks?limit=40");
  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="soft-panel-title">任务列表</p>
        <p className="soft-panel-sub font-mono text-[11px]">/api/tasks?limit=40</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      <DataTable rows={rowsOf(data, "tasks")} cols={taskCols} empty="暂无任务" />
    </div>
  );
}

export function HumanQueueTablePage() {
  const { data, err } = useFetchRow("/api/human-queue?status=pending");
  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="soft-panel-title">人工待办</p>
        <p className="soft-panel-sub font-mono text-[11px]">/api/human-queue?status=pending</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      <DataTable rows={rowsOf(data, "items")} cols={hqCols} empty="无待办事项" />
    </div>
  );
}
