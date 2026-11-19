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

  return (
    <>
      <ConsolePageHeader
        title="Agent 与岗位"
        description="Agent 台账、框架与启停；岗位和能力来自组织模块"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

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
                <button
                  type="button"
                  className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                  disabled={!can("system_config")}
                  onClick={() => void toggleAgent(row)}
                >
                  {row.enabled ? "停用" : "启用"}
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
