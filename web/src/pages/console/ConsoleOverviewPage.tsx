import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection } from "../../components/console/ConsoleKit";

type Overview = {
  employees_total: number;
  employees_active: number;
  employees_pending: number;
  employees_offline: number;
  agents_total: number;
  agents_enabled: number;
  agents_online: number;
  agents_busy: number;
  teams: number;
  positions: number;
  seats_occupied: number;
  tasks_total: number;
  tasks_active: number;
  tasks_running: number;
  tasks_blocked: number;
  tasks_done: number;
  tasks_failed_today: number;
  approvals_pending: number;
  messages_total: number;
  workflows_total: number;
  workflows_published: number;
  skills_total: number;
  skills_enabled: number;
};

/** 管理中心概览：所有数值均来自 GET /api/overview。 */
export function ConsoleOverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    void api<Overview>("/api/overview").then((result) => {
      if (!alive) return;
      setLoading(false);
      if (result.ok) {
        setOverview(result.data);
        setErr("");
      } else {
        setErr(result.error);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const value = (key: keyof Overview) => overview?.[key] ?? "—";

  return (
    <>
      <ConsolePageHeader
        title="管理中心"
        description="员工、Agent、任务、审批、消息与工作流的真实运营快照"
      />
      {err && <p className="mb-4 text-xs text-flare">{err}</p>}
      {loading && <p className="mb-4 text-xs text-mute">正在加载运营总览…</p>}

      <ConsoleSection title="当前工作负载">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="活跃任务" value={value("tasks_active")} />
          <Stat label="运行中" value={value("tasks_running")} />
          <Stat label="阻塞任务" value={value("tasks_blocked")} danger />
          <Stat label="待裁决审批" value={value("approvals_pending")} />
          <Stat label="在线 Agent" value={value("agents_online")} />
          <Stat label="忙碌 Agent" value={value("agents_busy")} />
          <Stat label="离线员工" value={value("employees_offline")} danger />
          <Stat label="今日失败任务" value={value("tasks_failed_today")} danger />
        </div>
      </ConsoleSection>

      <ConsoleSection title="组织与实体规模">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="员工总数" value={value("employees_total")} />
          <Stat label="在职员工" value={value("employees_active")} />
          <Stat label="待审核员工" value={value("employees_pending")} />
          <Stat label="已占用工位" value={value("seats_occupied")} />
          <Stat label="团队" value={value("teams")} />
          <Stat label="岗位" value={value("positions")} />
          <Stat label="Agent（启用/总数）" value={`${value("agents_enabled")} / ${value("agents_total")}`} />
          <Stat label="技能包（启用/总数）" value={`${value("skills_enabled")} / ${value("skills_total")}`} />
          <Stat label="消息总量" value={value("messages_total")} />
        </div>
      </ConsoleSection>

      <ConsoleSection title="交付累计">
        <div className="grid gap-2.5 sm:grid-cols-3">
          <Stat label="任务（完成/总数）" value={`${value("tasks_done")} / ${value("tasks_total")}`} />
          <Stat label="工作流（已发布/总数）" value={`${value("workflows_published")} / ${value("workflows_total")}`} />
          <Stat label="待审核员工" value={value("employees_pending")} />
        </div>
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
