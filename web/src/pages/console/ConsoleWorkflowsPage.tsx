import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

/** 工作流模板管理（P3）— 只读清单（编辑能力随 mailbus_workflow section 后续批次接入）。 */

type Workflow = {
  id: string;
  version?: string;
  display?: { zh?: string; en?: string };
  mode?: string;
  task_types?: string[];
  tags?: string[];
  phase_count?: number;
  gate_count?: number;
  steps?: Array<{ role_type?: number; label?: string; desc?: string }>;
};

export function ConsoleWorkflowsPage() {
  const [rows, setRows] = useState<Workflow[]>([]);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<Workflow | null>(null);

  useEffect(() => {
    void api<{ workflows?: Workflow[] }>("/api/workflows").then((r) => {
      if (r.ok && r.data?.workflows) setRows(r.data.workflows);
      else if (!r.ok) setErr(r.error);
    });
  }, []);

  return (
    <>
      <ConsolePageHeader title="工作流模板" description="工单链路模板（发令窗口的模板来源）；编辑能力随后续批次接入" />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      <ConsoleSection title={`模板（${rows.length}）`}>
        <ConsoleTable
          rows={rows}
          rowKey={(r) => r.id}
          onRowClick={setSel}
          selectedKey={sel?.id}
          columns={[
            { key: "id", header: "ID", render: (r) => <span className="font-mono">{r.id}</span> },
            { key: "name", header: "名称", render: (r) => r.display?.zh || r.display?.en || "—" },
            { key: "mode", header: "模式", render: (r) => <ConsoleTag>{r.mode || "—"}</ConsoleTag> },
            {
              key: "tt",
              header: "适用 task_type",
              render: (r) => <span className="font-mono text-mute">{(r.task_types || []).join(", ") || "—"}</span>,
            },
            { key: "ph", header: "阶段", render: (r) => String(r.phase_count ?? "—") },
            { key: "gt", header: "闸门", render: (r) => String(r.gate_count ?? "—") },
          ]}
        />
      </ConsoleSection>
      {sel && (
        <ConsoleSection title={`模板详情：${sel.display?.zh || sel.id}`}>
          <pre className="max-h-80 overflow-auto rounded-lg border border-rail bg-hull/40 p-3 font-mono text-[11px] text-frost/80">
            {JSON.stringify(sel, null, 2)}
          </pre>
        </ConsoleSection>
      )}
    </>
  );
}
