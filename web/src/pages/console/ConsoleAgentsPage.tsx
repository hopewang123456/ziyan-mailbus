import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

type AgentRow = {
  agent_id: string;
  name: string;
  framework: string;
  model?: string | null;
  endpoint?: string | null;
  enabled: boolean;
};

type PositionRow = {
  position_id: string;
  name: string;
  capabilities: string[];
};

/** Agent 台账与组织岗位，严格使用当前 agents/org 契约。 */
export function ConsoleAgentsPage({ can }: { can: (capability: string) => boolean }) {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [framework, setFramework] = useState("");
  const [model, setModel] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const systemConfig = can("system_config");

  const load = async () => {
    setLoading(true);
    const [agentResult, positionResult] = await Promise.all([
      api<AgentRow[]>("/api/agents"),
      api<PositionRow[]>("/api/org/positions"),
    ]);
    setLoading(false);
    if (agentResult.ok) setAgents(agentResult.data);
    if (positionResult.ok) setPositions(positionResult.data);
    const errors = [agentResult, positionResult]
      .filter((result) => !result.ok)
      .map((result) => (result.ok ? "" : result.error));
    setErr(errors.filter(Boolean).join("; "));
  };

  useEffect(() => {
    void load();
  }, []);

  function resetForm() {
    setEditingId(null);
    setName("");
    setFramework("");
    setModel("");
    setEndpoint("");
  }

  async function saveAgent() {
    setErr("");
    setMsg("");
    if (!name.trim()) {
      setErr("Agent 名称不能为空");
      return;
    }
    setCreating(true);
    const body = JSON.stringify({
      name: name.trim(),
      framework: framework.trim(),
      model: model.trim() || null,
      endpoint: endpoint.trim() || null,
    });
    const result = await api<AgentRow>(
      editingId ? `/api/agents/${encodeURIComponent(editingId)}` : "/api/agents",
      { method: editingId ? "PATCH" : "POST", body },
    );
    setCreating(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    if (editingId) {
      setAgents((rows) =>
        rows.map((row) => (row.agent_id === editingId ? result.data : row)),
      );
      setMsg(`已更新 Agent「${result.data.name}」`);
    } else {
      setAgents((rows) => [result.data, ...rows]);
      setMsg(`已登记 Agent「${result.data.name}」`);
    }
    resetForm();
  }

  function startEdit(agent: AgentRow) {
    setEditingId(agent.agent_id);
    setName(agent.name);
    setFramework(agent.framework);
    setModel(agent.model ?? "");
    setEndpoint(agent.endpoint ?? "");
    setErr("");
    setMsg("");
  }

  async function toggleAgent(agent: AgentRow) {
    setErr("");
    setMsg("");
    const result = await api<AgentRow>(`/api/agents/${encodeURIComponent(agent.agent_id)}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !agent.enabled }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setAgents((rows) => rows.map((row) => row.agent_id === agent.agent_id ? result.data : row));
    setMsg(`已${result.data.enabled ? "启用" : "停用"}「${result.data.name}」`);
  }

  async function removeAgent(agent: AgentRow) {
    setErr("");
    setMsg("");
    const result = await api(`/api/agents/${encodeURIComponent(agent.agent_id)}`, {
      method: "DELETE",
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    if (editingId === agent.agent_id) resetForm();
    setAgents((rows) => rows.filter((row) => row.agent_id !== agent.agent_id));
    setMsg(`已删除 Agent「${agent.name}」`);
  }

  return (
    <>
      <ConsolePageHeader
        title="Agent 与岗位"
        description="Agent 台账、框架与启停；岗位和能力来自组织模块"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      {systemConfig && (
        <ConsoleSection title={editingId ? `编辑 Agent（${editingId}）` : "登记 Agent"}>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-mute">
              名称
              <input
                className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                placeholder="必填"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-mute">
              框架
              <input
                className="mt-1 block w-32 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                placeholder="claude / openai"
                value={framework}
                onChange={(e) => setFramework(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-mute">
              模型
              <input
                className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                placeholder="可选"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </label>
            <label className="flex-1 text-[11px] text-mute">
              端点
              <input
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1 font-mono text-xs text-frost"
                placeholder="http://127.0.0.1:8000/agent"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={creating}
              onClick={() => void saveAgent()}
            >
              {creating ? "保存中…" : editingId ? "保存修改" : "登记"}
            </button>
            {editingId && (
              <button
                type="button"
                className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
                onClick={resetForm}
              >
                取消
              </button>
            )}
          </div>
        </ConsoleSection>
      )}

      <ConsoleSection title={`岗位（${positions.length}）`}>
        <ConsoleTable
          rows={positions}
          rowKey={(row) => row.position_id}
          loading={loading}
          empty="暂无岗位"
          columns={[
            { key: "id", header: "position_id", render: (row) => <span className="font-mono">{row.position_id}</span> },
            { key: "name", header: "岗位", render: (row) => row.name },
            {
              key: "caps",
              header: "能力",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  {row.capabilities.length
                    ? row.capabilities.map((capability) => <ConsoleTag key={capability}>{capability}</ConsoleTag>)
                    : "—"}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title={`Agent（${agents.length}）`}>
        <ConsoleTable
          rows={agents}
          rowKey={(row) => row.agent_id}
          loading={loading}
          empty="暂无 Agent"
          columns={[
            { key: "id", header: "ID", render: (row) => <span className="font-mono">{row.agent_id}</span> },
            { key: "name", header: "名称", render: (row) => row.name },
            { key: "framework", header: "框架", render: (row) => <ConsoleTag>{row.framework || "—"}</ConsoleTag> },
            { key: "model", header: "模型", render: (row) => row.model || "—" },
            { key: "endpoint", header: "端点", render: (row) => <span className="font-mono text-[11px]">{row.endpoint || "—"}</span> },
            {
              key: "status",
              header: "状态",
              render: (row) => <ConsoleTag tone={row.enabled ? "ok" : "danger"}>{row.enabled ? "启用" : "停用"}</ConsoleTag>,
            },
            {
              key: "action",
              header: "操作",
              render: (row) => (
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                    disabled={!can("system_config")}
                    onClick={() => startEdit(row)}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                    disabled={!can("system_config")}
                    onClick={() => void toggleAgent(row)}
                  >
                    {row.enabled ? "停用" : "启用"}
                  </button>
                  <button
                    type="button"
                    className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                    disabled={!can("system_config")}
                    onClick={() => void removeAgent(row)}
                  >
                    删除
                  </button>
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
