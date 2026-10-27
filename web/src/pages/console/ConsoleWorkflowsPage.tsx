import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

/**
 * 工作流模板管理 — 只读 → 可编辑（交接③：发令「选模板」闭环的管理侧）。
 * 后端契约（python handlers_workflows；java 对等见 WorkflowsController）：
 *   GET /api/workflows · GET /api/workflows/{id} ·
 *   POST /api/workflows/{id} {workflow} · POST /api/workflows/{id}/delete
 * 真源：{data_dir}/workflows/registry.json（双栈共享 SoT）。
 */

type Workflow = {
  id: string;
  version?: string;
  display?: { zh?: string; en?: string };
  mode?: string;
  task_types?: string[];
  tags?: string[];
  llm_policy?: unknown;
  gates?: unknown[];
  phases?: Array<{ id?: string; display?: { zh?: string }; steps?: Array<{ node_type?: string; role_type?: number }> }>;
  phase_count?: number;
  gate_count?: number;
};

type EditState = {
  orig: Workflow;
  zh: string;
  en: string;
  mode: string;
  version: string;
  taskTypes: string;
  tags: string;
  phasesJson: string;
  gatesJson: string;
  llmPolicyJson: string;
};

function toEdit(wf: Workflow): EditState {
  return {
    orig: wf,
    zh: wf.display?.zh || "",
    en: wf.display?.en || "",
    mode: wf.mode || "",
    version: wf.version || "",
    taskTypes: (wf.task_types || []).join(", "),
    tags: (wf.tags || []).join(", "),
    phasesJson: JSON.stringify(wf.phases ?? [], null, 2),
    gatesJson: JSON.stringify(wf.gates ?? [], null, 2),
    llmPolicyJson: wf.llm_policy === undefined ? "" : JSON.stringify(wf.llm_policy, null, 2),
  };
}

function fromEdit(e: EditState, id: string): Workflow {
  const wf: Workflow = { ...e.orig, id };
  wf.version = e.version.trim() || undefined;
  wf.display = { zh: e.zh.trim() || undefined, en: e.en.trim() || undefined };
  wf.mode = e.mode.trim() || undefined;
  wf.task_types = e.taskTypes.split(",").map((s) => s.trim()).filter(Boolean);
  wf.tags = e.tags.split(",").map((s) => s.trim()).filter(Boolean);
  wf.phases = JSON.parse(e.phasesJson || "[]");
  wf.gates = JSON.parse(e.gatesJson || "[]");
  if (e.llmPolicyJson.trim()) wf.llm_policy = JSON.parse(e.llmPolicyJson);
  else delete wf.llm_policy;
  return wf;
}

function jsonParses(s: string): boolean {
  if (!s.trim()) return true;
  try {
    JSON.parse(s);
    return true;
  } catch {
    return false;
  }
}

export function ConsoleWorkflowsPage() {
  const [rows, setRows] = useState<Workflow[]>([]);
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState<EditState | null>(null);
  const [newId, setNewId] = useState("");
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload(selectId?: string) {
    const r = await api<{ workflows?: Workflow[] }>("/api/workflows");
    if (r.ok && r.data?.workflows) {
      setRows(r.data.workflows);
      if (selectId && r.data.workflows.some((w) => w.id === selectId)) void openEdit(selectId);
    } else if (!r.ok) setErr(r.error);
  }

  useEffect(() => {
    void reload();
  }, []);

  async function openEdit(id: string) {
    setMsg("");
    const r = await api<{ workflow?: Workflow }>(`/api/workflows/${encodeURIComponent(id)}`);
    const wf = r.ok ? r.data?.workflow : undefined;
    if (wf) {
      setEdit(toEdit(wf));
      setCreating(false);
      setNewId("");
    } else if (!r.ok) setErr(r.error);
  }

  async function save() {
    if (!edit || busy) return;
    const id = creating ? newId.trim() : edit.orig.id;
    if (!/^[a-z][a-z0-9_]{1,63}$/.test(id)) {
      setMsg("✗ id 规则：小写字母开头，2-64 位 [a-z0-9_]");
      return;
    }
    let wf: Workflow;
    try {
      wf = fromEdit(edit, id);
    } catch {
      setMsg("✗ JSON 段格式错误（phases/gates/llm_policy）");
      return;
    }
    setBusy(true);
    const r = await api<{ created?: boolean }>(`/api/workflows/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ workflow: wf }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`✓ 已保存（${r.data?.created ? "新建" : "更新"}：${id}）`);
      setCreating(false);
      await reload(id);
    } else setMsg(`✗ 保存失败：${r.error}`);
  }

  async function remove() {
    if (!edit || creating || busy) return;
    if (!window.confirm(`删除模板 ${edit.orig.id}？不可恢复。`)) return;
    setBusy(true);
    const r = await api(`/api/workflows/${encodeURIComponent(edit.orig.id)}/delete`, { method: "POST" });
    setBusy(false);
    if (r.ok) {
      setMsg(`✓ 已删除 ${edit.orig.id}`);
      setEdit(null);
      await reload();
    } else setMsg(`✗ 删除失败：${r.error}`);
  }

  const jsonOk = edit
    ? [edit.phasesJson, edit.gatesJson, edit.llmPolicyJson].every(jsonParses)
    : true;

  return (
    <>
      <ConsolePageHeader
        title="工作流模板"
        description="工单链路模板（发令窗口「从模板起草」的来源）；编辑写回 registry.json（双栈共享 SoT）"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className={msg.startsWith("✓") ? "mb-3 text-xs text-mint" : "mb-3 text-xs text-flare"}>{msg}</p>}

      <ConsoleSection
        title={`模板（${rows.length}）`}
        actions={
          <button
            className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
            onClick={() => {
              setEdit(toEdit({ id: "", phases: [], gates: [] }));
              setNewId("");
              setCreating(true);
              setMsg("");
            }}
          >
            ＋ 新建模板
          </button>
        }
      >
        <ConsoleTable
          rows={rows}
          rowKey={(r) => r.id}
          onRowClick={(r) => void openEdit(r.id)}
          selectedKey={creating ? undefined : edit?.orig.id}
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

      {edit && (
        <ConsoleSection title={creating ? "新建模板" : `编辑：${edit.orig.display?.zh || edit.orig.id}`}>
          <div className="space-y-2">
            {creating ? (
              <label className="flex items-center gap-2 text-[11px] text-mute">
                id（小写字母开头，[a-z0-9_]，2-64 位）
                <input
                  className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={newId}
                  onChange={(e) => setNewId(e.target.value)}
                  placeholder="my_pipeline"
                />
              </label>
            ) : (
              <p className="mb-2 text-[11px] text-mute">
                id <span className="font-mono">{edit.orig.id}</span>（不可改）；保存写回 registry.json
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <label className="flex flex-1 items-center gap-2 text-[11px] text-mute">
                名称（中）
                <input
                  className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 text-xs text-frost"
                  value={edit.zh}
                  onChange={(e) => setEdit({ ...edit, zh: e.target.value })}
                />
              </label>
              <label className="flex flex-1 items-center gap-2 text-[11px] text-mute">
                名称（英）
                <input
                  className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 text-xs text-frost"
                  value={edit.en}
                  onChange={(e) => setEdit({ ...edit, en: e.target.value })}
                />
              </label>
              <label className="flex items-center gap-2 text-[11px] text-mute">
                mode
                <input
                  className="w-32 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={edit.mode}
                  onChange={(e) => setEdit({ ...edit, mode: e.target.value })}
                />
              </label>
              <label className="flex items-center gap-2 text-[11px] text-mute">
                version
                <input
                  className="w-24 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={edit.version}
                  onChange={(e) => setEdit({ ...edit, version: e.target.value })}
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <label className="flex flex-1 items-center gap-2 text-[11px] text-mute">
                task_types（逗号分隔）
                <input
                  className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={edit.taskTypes}
                  onChange={(e) => setEdit({ ...edit, taskTypes: e.target.value })}
                />
              </label>
              <label className="flex flex-1 items-center gap-2 text-[11px] text-mute">
                tags（逗号分隔）
                <input
                  className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={edit.tags}
                  onChange={(e) => setEdit({ ...edit, tags: e.target.value })}
                />
              </label>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <label className="text-[11px] text-mute">
                phases（JSON；steps[].role_type 为发令模板链来源）
                <textarea
                  className="mt-1 h-40 w-full rounded border border-rail bg-hull/40 p-2 font-mono text-[11px] text-frost"
                  value={edit.phasesJson}
                  onChange={(e) => setEdit({ ...edit, phasesJson: e.target.value })}
                  spellCheck={false}
                />
              </label>
              <label className="text-[11px] text-mute">
                gates（JSON）
                <textarea
                  className="mt-1 h-40 w-full rounded border border-rail bg-hull/40 p-2 font-mono text-[11px] text-frost"
                  value={edit.gatesJson}
                  onChange={(e) => setEdit({ ...edit, gatesJson: e.target.value })}
                  spellCheck={false}
                />
              </label>
            </div>
            <label className="text-[11px] text-mute">
              llm_policy（JSON，可空）
              <textarea
                className="mt-1 h-20 w-full rounded border border-rail bg-hull/40 p-2 font-mono text-[11px] text-frost"
                value={edit.llmPolicyJson}
                onChange={(e) => setEdit({ ...edit, llmPolicyJson: e.target.value })}
                spellCheck={false}
              />
            </label>
            {!jsonOk && <p className="text-xs text-flare">JSON 段格式错误，无法保存</p>}
            <div className="flex items-center gap-2">
              <button className="hud-btn text-xs" disabled={busy || !jsonOk} onClick={() => void save()}>
                {busy ? "保存中…" : creating ? "创建" : "保存"}
              </button>
              {!creating && (
                <button
                  className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-flare"
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  删除
                </button>
              )}
              <button
                className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
                onClick={() => {
                  setEdit(null);
                  setCreating(false);
                  setMsg("");
                }}
              >
                关闭
              </button>
            </div>
          </div>
        </ConsoleSection>
      )}
    </>
  );
}
