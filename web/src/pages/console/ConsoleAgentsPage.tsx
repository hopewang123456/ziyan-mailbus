import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

/** Agent 与职位管理（P3）— 职位是发令窗口的表单来源（inputs schema），故可编辑。 */

type AgentRow = {
  id: string;
  name?: string;
  role?: string;
  type?: string;
  framework?: string;
  models?: string[];
  enabled?: boolean;
  builtin?: boolean;
};
type PositionRow = {
  role_type: number;
  key: string;
  name_zh: string;
  name_en: string;
  default_sla_minutes?: number | null;
  inputs: InputField[];
  candidates: Array<{ agent_id: string; name: string; framework: string; available: boolean; busy: boolean; active_tasks: number }>;
};
type InputField = {
  name: string;
  label?: { zh?: string; en?: string };
  type: string;
  required?: boolean;
  default?: string | number | boolean;
  options?: string[];
};

export function ConsoleAgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [sel, setSel] = useState<PositionRow | null>(null);
  const [draftInputs, setDraftInputs] = useState<InputField[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    const [a, p] = await Promise.all([
      api<{ agents?: Record<string, Omit<AgentRow, "id">> }>("/api/agents"),
      api<{ positions?: PositionRow[] }>("/api/positions"),
    ]);
    if (a.ok && a.data?.agents) {
      setAgents(
        Object.entries(a.data.agents).map(([id, v]) => ({ id, ...v })),
      );
    }
    if (p.ok && p.data?.positions) setPositions(p.data.positions);
    if (!a.ok) setErr(a.error);
    if (!p.ok) setErr(p.error);
  };

  useEffect(() => {
    void load();
  }, []);

  function pick(pos: PositionRow) {
    setSel(pos);
    setDraftInputs(JSON.parse(JSON.stringify(pos.inputs || [])) as InputField[]);
    setMsg("");
  }

  async function saveInputs() {
    if (!sel) return;
    const r = await api<{ entry?: unknown }>(`/api/positions/${sel.role_type}`, {
      method: "PATCH",
      body: JSON.stringify({ fields: { inputs: draftInputs } }),
    });
    if (r.ok) {
      setMsg(`职位「${sel.name_zh}」的表单 schema 已保存（发令窗口立即生效）`);
      await load();
      setSel((s) => (s ? { ...s, inputs: draftInputs } : s));
    } else {
      setErr("error" in r ? String(r.error) : "保存失败");
    }
  }

  async function toggleAgent(a: AgentRow) {
    const r = await api("/api/settings/section/agents", {
      method: "PATCH",
      body: JSON.stringify({ agent_id: a.id, fields: { enabled: !(a.enabled !== false) } }),
    });
    if (r.ok) await load();
    else setErr("error" in r ? String(r.error) : "保存失败");
  }

  return (
    <>
      <ConsolePageHeader
        title="Agent 与职位"
        description="Agent 启停与角色信息；职位（role_type）是发令窗口的节点与表单 schema 来源"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection title={`职位（${positions.length}）— 点击行编辑表单 schema`}>
        <ConsoleTable
          rows={positions}
          rowKey={(r) => String(r.role_type)}
          onRowClick={pick}
          selectedKey={sel ? String(sel.role_type) : undefined}
          columns={[
            { key: "rt", header: "role_type", render: (r) => <span className="font-mono">{r.role_type}</span> },
            { key: "name", header: "职位", render: (r) => r.name_zh || r.key },
            { key: "key", header: "key", render: (r) => <span className="font-mono text-mute">{r.key}</span> },
            {
              key: "cand",
              header: "候选",
              render: (r) => (
                <span className="text-mute">
                  {(r.candidates || []).map((c) => c.agent_id).join(", ") || "—"}
                </span>
              ),
            },
            {
              key: "inputs",
              header: "表单字段",
              render: (r) =>
                r.inputs?.length ? (
                  <span className="flex flex-wrap gap-1">
                    {r.inputs.map((f) => (
                      <ConsoleTag key={f.name} tone={f.required ? "ok" : "default"}>
                        {f.name}
                      </ConsoleTag>
                    ))}
                  </span>
                ) : (
                  <span className="text-mute">未配置</span>
                ),
            },
            { key: "sla", header: "SLA(分)", render: (r) => (r.default_sla_minutes ?? "—") as string | number },
          ]}
        />
      </ConsoleSection>

      {sel && (
        <ConsoleSection
          title={`编辑职位「${sel.name_zh}」的表单 schema`}
          actions={
            <button type="button" className="hud-btn text-xs" onClick={() => void saveInputs()}>
              保存
            </button>
          }
        >
          <p className="mb-2 text-[11px] text-mute">
            字段：name / 类型（string·text·enum·number·boolean）/ 必填 / 选项 / 默认值。保存后发令窗口按此渲染。
          </p>
          <div className="space-y-2">
            {draftInputs.map((f, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 rounded border border-rail bg-hull/40 p-2">
                <input
                  className="w-28 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                  value={f.name}
                  placeholder="name"
                  onChange={(e) =>
                    setDraftInputs((d) => d.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)))
                  }
                />
                <select
                  className="rounded border border-rail bg-hull px-1.5 py-1 text-xs text-frost"
                  value={f.type}
                  onChange={(e) =>
                    setDraftInputs((d) => d.map((x, k) => (k === i ? { ...x, type: e.target.value } : x)))
                  }
                >
                  {["string", "text", "enum", "number", "boolean"].map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-1 text-[11px] text-mute">
                  <input
                    type="checkbox"
                    className="accent-mint"
                    checked={!!f.required}
                    onChange={(e) =>
                      setDraftInputs((d) => d.map((x, k) => (k === i ? { ...x, required: e.target.checked } : x)))
                    }
                  />
                  必填
                </label>
                {f.type === "enum" && (
                  <input
                    className="flex-1 rounded border border-rail bg-hull px-1.5 py-1 font-mono text-xs text-frost"
                    value={(f.options || []).join(",")}
                    placeholder="选项，逗号分隔"
                    onChange={(e) =>
                      setDraftInputs((d) =>
                        d.map((x, k) =>
                          k === i ? { ...x, options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } : x,
                        ),
                      )
                    }
                  />
                )}
                <button
                  type="button"
                  className="text-mute hover:text-flare"
                  title="删除字段"
                  onClick={() => setDraftInputs((d) => d.filter((_, k) => k !== i))}
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
              onClick={() => setDraftInputs((d) => [...d, { name: "", type: "string", required: false }])}
            >
              + 添加字段
            </button>
          </div>
        </ConsoleSection>
      )}

      <ConsoleSection title={`Agent（${agents.length}）`}>
        <ConsoleTable
          rows={agents}
          rowKey={(r) => r.id}
          columns={[
            { key: "id", header: "ID", render: (r) => <span className="font-mono">{r.id}</span> },
            { key: "name", header: "名称", render: (r) => r.name || "—" },
            { key: "role", header: "角色", render: (r) => r.role || "—" },
            {
              key: "type",
              header: "框架",
              render: (r) => <ConsoleTag>{r.framework || r.type || "—"}</ConsoleTag>,
            },
            { key: "models", header: "模型", render: (r) => <span className="text-mute">{(r.models || []).join(", ") || "—"}</span> },
            {
              key: "st",
              header: "状态",
              render: (r) => (
                <ConsoleTag tone={r.builtin ? "ok" : r.enabled === false ? "danger" : "default"}>
                  {r.builtin ? "内置" : r.enabled === false ? "停用" : "启用"}
                </ConsoleTag>
              ),
            },
            {
              key: "act",
              header: "操作",
              render: (r) =>
                r.builtin ? (
                  <span className="text-mute">内置身份</span>
                ) : (
                  <button
                    type="button"
                    className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                    onClick={() => void toggleAgent(r)}
                  >
                    {r.enabled === false ? "启用" : "停用"}
                  </button>
                ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
