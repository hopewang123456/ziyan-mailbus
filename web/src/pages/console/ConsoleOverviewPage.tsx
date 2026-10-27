import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

/** 管理中心概览（P3）— 系统健康 + 关键实体计数 + 指标快照（B 类报表入口）。 */

type MetricsResp = { points?: Array<{ metric?: string; value?: number; error?: string; unit?: string }> };
type AgentsResp = {
  agents?: Record<string, { name?: string; type?: string; role?: string; framework?: string }>;
};
type PositionsResp = { positions?: Array<{ role_type?: number; name_zh?: string; candidates?: unknown[] }> };
type IdentitiesResp = { identities?: Array<{ id?: string; display_name?: string; role?: string }> };
type ManagerResp = { counts?: Record<string, number>; total?: number };

export function ConsoleOverviewPage() {
  const [metrics, setMetrics] = useState<MetricsResp | null>(null);
  const [agents, setAgents] = useState<AgentsResp | null>(null);
  const [positions, setPositions] = useState<PositionsResp | null>(null);
  const [identities, setIdentities] = useState<IdentitiesResp | null>(null);
  const [manager, setManager] = useState<ManagerResp | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    void Promise.all([
      api<MetricsResp>("/api/metrics/query"),
      api<AgentsResp>("/api/agents"),
      api<PositionsResp>("/api/positions"),
      api<IdentitiesResp>("/api/identities"),
      api<ManagerResp>("/api/manager/pending"),
    ]).then(([m, a, p, i, mg]) => {
      if (m.ok && m.data) setMetrics(m.data);
      if (a.ok && a.data) setAgents(a.data);
      if (p.ok && p.data) setPositions(p.data);
      if (i.ok && i.data) setIdentities(i.data);
      if (mg.ok && mg.data) setManager(mg.data);
      const e = [m, a, p, i, mg].filter((r) => !r.ok).map((r) => ("error" in r ? r.error : ""));
      if (e.length) setErr(e.filter(Boolean).join("; "));
    });
  }, []);

  const points = metrics?.points || [];
  const m = (id: string) => points.find((p) => p.metric === id);
  const val = (id: string) => {
    const p = m(id);
    return p && p.value !== undefined ? p.value : "—";
  };

  return (
    <>
      <ConsolePageHeader
        title="管理中心"
        description="mailbus 协同管理总览 — 配置、管理、集成与指标治理（P3）"
      />
      {err && <p className="mb-4 text-xs text-flare">{err}</p>}

      <ConsoleSection title="关键指标（口径 SoT：metrics-manifest.json）">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="活跃任务" value={val("tasks.active")} />
          <Stat label="未读消息" value={val("bus.unread")} />
          <Stat label="在线 agent" value={val("agents.online")} />
          <Stat label="活跃告警" value={val("alerts.active")} danger />
          <Stat label="消息总量" value={val("bus.messages_total")} />
          <Stat label="人工待办" value={val("humanqueue.pending")} />
          <Stat label="今日失败" value={val("tasks.failed_today")} danger />
          <Stat label="今日 Token（估）" value={val("tokens.today_estimated")} />
        </div>
      </ConsoleSection>

      <ConsoleSection title="实体规模">
        <div className="grid gap-2.5 sm:grid-cols-3">
          <Stat label="注册 agent" value={Object.keys(agents?.agents || {}).length || "—"} />
          <Stat label="职位（role_type）" value={positions?.positions?.length ?? "—"} />
          <Stat label="内置身份" value={identities?.identities?.length ?? "—"} />
        </div>
      </ConsoleSection>

      <ConsoleSection title="内置身份（D2/D15）">
        <ConsoleTable
          rows={identities?.identities || []}
          rowKey={(r, i) => String(r.id || i)}
          empty="未发现内置身份"
          columns={[
            { key: "id", header: "身份 ID", render: (r) => <span className="font-mono">{r.id}</span> },
            { key: "name", header: "显示名", render: (r) => r.display_name || "—" },
            { key: "role", header: "角色", render: (r) => <ConsoleTag>{r.role || "—"}</ConsoleTag> },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title="待我处理（协调台聚合）">
        <ConsoleTable
          rows={Object.entries(manager?.counts || {}).map(([k, v]) => ({ k, v }))}
          rowKey={(r) => r.k}
          empty="暂无待处理事项"
          columns={[
            { key: "k", header: "类别", render: (r) => r.k },
            { key: "v", header: "数量", render: (r) => String(r.v) },
          ]}
        />
      </ConsoleSection>
    </>
  );
}

function Stat({ label, value, danger }: { label: string; value: number | string; danger?: boolean }) {
  const bad = danger && typeof value === "number" && value > 0;
  return (
    <div className="rounded-lg border border-rail bg-hull/50 px-3 py-2.5">
      <p className="text-[11px] text-mute">{label}</p>
      <p className={`mt-1 font-mono text-lg ${bad ? "text-flare" : "text-frost"}`}>{value}</p>
    </div>
  );
}
