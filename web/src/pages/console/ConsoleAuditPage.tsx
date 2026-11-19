import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

/** 审计与告警（P3）— 审核统计 + 最近告警（告警规则在「指标与报表」页管理）。 */

type AuditStats = {
  total_tasks?: number;
  audited_tasks?: number;
  pending_audit_tasks?: number;
  pass_count?: number;
  fail_count?: number;
  warn_count?: number;
  by_reviewer?: Record<string, { pass?: number; fail?: number; warn?: number; total?: number }>;
};
type Alert = {
  id: string;
  type?: string;
  severity?: string;
  agent?: string;
  message?: string;
  ts?: string;
};

export function ConsoleAuditPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const [s, a] = await Promise.all([
      api<AuditStats>("/api/tasks/audit/stats"),
      api<{ alerts?: Alert[] }>("/api/alerts"),
    ]);
    setLoading(false);
    if (s.ok && s.data) setStats(s.data);
    if (a.ok && a.data?.alerts) setAlerts(a.data.alerts);
    const errors = [s, a].filter((r) => !r.ok).map((r) => (r.ok ? "" : r.error));
    setErr(errors.filter(Boolean).join("；"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sevTone = (s?: string) => (s === "critical" ? "danger" : s === "warn" ? "warn" : "default");

  return (
    <>
      <ConsolePageHeader
        title="审计与告警"
        description="工单审核统计与最近告警（规则编辑在「指标与报表」）"
        actions={
          <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
            刷新
          </button>
        }
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}

      <ConsoleSection title="审核统计">
        <div className="mb-4 grid gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="总任务" value={stats?.total_tasks ?? "—"} />
          <Stat label="已审" value={stats?.audited_tasks ?? "—"} />
          <Stat label="待审" value={stats?.pending_audit_tasks ?? "—"} />
          <Stat label="不通过" value={stats?.fail_count ?? "—"} danger />
          <Stat label="告警（未消）" value={alerts.length} danger={alerts.length > 0} />
        </div>
        <ConsoleTable
          rows={Object.entries(stats?.by_reviewer || {}).map(([k, v]) => ({ reviewer: k, ...v }))}
          rowKey={(r) => r.reviewer}
          loading={loading}
          empty="暂无审核数据"
          columns={[
            { key: "r", header: "审核人", render: (r) => <span className="font-mono">{r.reviewer}</span> },
            { key: "p", header: "通过", render: (r) => String(r.pass ?? 0) },
            { key: "w", header: "警告", render: (r) => String(r.warn ?? 0) },
            { key: "f", header: "不通过", render: (r) => String(r.fail ?? 0) },
            { key: "t", header: "合计", render: (r) => String(r.total ?? 0) },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title={`最近告警（${alerts.length}）`}>
        <ConsoleTable
          rows={alerts}
          rowKey={(a, i) => a.id || String(i)}
          loading={loading}
          empty="暂无告警"
          columns={[
            {
              key: "sev",
              header: "级别",
              render: (a) => <ConsoleTag tone={sevTone(a.severity) as "danger" | "warn" | "default"}>{a.severity || "info"}</ConsoleTag>,
            },
            { key: "type", header: "类型", render: (a) => <span className="font-mono">{a.type || "—"}</span> },
            { key: "agent", header: "对象", render: (a) => a.agent || "—" },
            { key: "msg", header: "消息", render: (a) => <span className="text-mute">{(a.message || "").slice(0, 70)}</span> },
            { key: "ts", header: "时间", render: (a) => <span className="text-mute">{a.ts || "—"}</span> },
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
