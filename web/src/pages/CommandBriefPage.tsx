import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "../components/ErrorAlert";

type StatusResp = {
  version?: string;
  status?: string;
  agents?: number;
  unread_messages?: number;
  total_messages?: number;
};
type StatsResp = {
  total_messages?: number;
  agent_stats?: Record<string, { total: number; type: string; role: string }>;
  task_statuses?: Record<string, number>;
  agent_count?: number;
};
type DoctorResp = {
  ok?: boolean;
  issues?: number;
  warnings?: number;
  items?: Array<{ level: string; category: string; message: string; detail?: string }>;
};
type WorkloadResp = {
  agents?: Record<string, {
    name?: string;
    active_tasks?: number;
    queued_steps?: number;
    inbox_pending?: number;
  }>;
};

/** 舰桥首页 → 指挥摘要 */
export function CommandBriefPage() {
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [stats, setStats] = useState<StatsResp | null>(null);
  const [doctor, setDoctor] = useState<DoctorResp | null>(null);
  const [workload, setWorkload] = useState<WorkloadResp | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([
      api<StatusResp>("/api/status"),
      api<StatsResp>("/api/stats"),
      api<DoctorResp>("/api/doctor"),
      api<WorkloadResp>("/api/workload"),
    ]).then(([sR, stR, dR, wR]) => {
      if (sR.ok) setStatus(sR.data);
      if (stR.ok) setStats(stR.data);
      if (dR.ok) setDoctor(dR.data);
      if (wR.ok) setWorkload(wR.data);
      const errors = [sR, stR, dR, wR].filter((r) => !r.ok).map((r) => r.error).filter(Boolean);
      if (errors.length) setErr(errors.join("; "));
    });
  }, []);

  async function sendPing() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/send-msg", {
      method: "POST",
      body: JSON.stringify({ text: "[舰桥] ping", channel: "default" }),
    });
    setBusy(false);
    setMsg(r.ok ? "已发送" : r.error);
  }

  // ── 统计摘要 ──
  const failedTasks = (stats?.task_statuses?.failed || 0) + (stats?.task_statuses?.timeout || 0);
  const doctorIssues = (doctor?.issues || 0) + (doctor?.warnings || 0);

  // Agent 负载 top 问题
  const wlAgents = workload?.agents || {};
  const busyAgents = Object.entries(wlAgents)
    .filter(([, a]) => (a.active_tasks || 0) > 0 || (a.inbox_pending || 0) > 0)
    .sort(([, a], [, b]) => (b.active_tasks || 0) - (a.active_tasks || 0))
    .slice(0, 5);

  return (
    <div className="space-y-4" data-surface="fleet">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="hud-label">Command</p>
          <h2 className="mt-1 font-display text-xl text-frost">指挥摘要</h2>
        </div>
        <div className="flex gap-2">
          <button type="button" className="hud-btn text-xs" disabled={busy} onClick={() => void sendPing()}>
            发 Ping
          </button>
        </div>
      </header>

      {/* 总线状态 */}
      <div className="rounded-sm border border-rail bg-hull/50 px-3 py-2 text-xs">
        <span className="text-mute">总线: </span>
        <span className={status?.status === "ok" || status?.version ? "text-mint" : "text-mute"}>
          {status?.version || status?.status || "…"}
        </span>
        <span className="text-mute ml-3">
          agents {status?.agents ?? "—"} · 消息 {status?.total_messages ?? "—"} · 未读 {status?.unread_messages ?? "—"}
        </span>
        {stats && (
          <span className="text-mute ml-3">
            统计: {stats.total_messages ?? "—"} 条 · {stats.agent_count ?? "—"} agent
          </span>
        )}
      </div>

      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-mint">{msg}</p>}

      {/* 关键指标 */}
      <div className="grid gap-3 sm:grid-cols-4">
        <IndicatorCard
          label="总线健康"
          value={doctor ? (doctorIssues === 0 ? "正常" : `${doctorIssues} 项`) : "…"}
          ok={doctor ? doctorIssues === 0 : undefined}
          color={doctorIssues > 0 ? "text-flare" : "text-mint"}
        />
        <IndicatorCard
          label="失败任务"
          value={stats ? String(failedTasks) : "…"}
          ok={stats ? failedTasks === 0 : undefined}
          color={failedTasks > 0 ? "text-flare" : "text-mint"}
        />
        <IndicatorCard
          label="运行中"
          value={stats ? String(stats.task_statuses?.running || 0) : "…"}
          ok={undefined}
          color="text-cyan-signal"
        />
        <IndicatorCard
          label="AgentMemory"
          value={stats ? "已连接" : "…"}
          ok={stats ? undefined : undefined}
          color={stats ? "text-mint" : "text-mute"}
        />
      </div>

      {/* Agent 工作负载 */}
      {busyAgents.length > 0 && (
        <div className="rounded-sm border border-rail bg-hull/50 p-3">
          <p className="hud-label mb-2">Agent 工作负载</p>
          <div className="space-y-1">
            {busyAgents.map(([id, a]) => (
              <div key={id} className="flex items-center gap-3 text-xs border-b border-rail/30 py-1">
                <span className="font-mono text-frost min-w-[60px]">{a.name || id}</span>
                {a.active_tasks ? <span className="text-amber-signal">⏳ {a.active_tasks} 任务</span> : null}
                {a.inbox_pending ? <span className="text-cyan-signal">📨 {a.inbox_pending} 待处理</span> : null}
                {a.queued_steps ? <span className="text-mute">📋 {a.queued_steps} 排队</span> : null}
                {!a.active_tasks && !a.inbox_pending && !a.queued_steps && (
                  <span className="text-mute">空闲</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Doctor 问题一览 */}
      {doctor && doctorIssues > 0 && (
        <div className="rounded-sm border border-flare/20 bg-flare/3 p-3">
          <p className="text-xs text-flare font-bold mb-2">
            ⚠ Doctor 发现 {doctorIssues} 项问题
          </p>
          <ul className="space-y-1 max-h-40 overflow-auto">
            {(doctor.items || [])
              .filter((i) => i.level !== "ok")
              .slice(0, 8)
              .map((item, idx) => (
                <li key={idx} className={`text-xs ${item.level === "fail" ? "text-flare" : "text-amber-signal"} border-l-2 border-current pl-2`}>
                  <span className="text-mute">[{item.category}]</span> {item.message}
                  {item.detail && <p className="font-mono text-[10px] text-mute truncate">{item.detail}</p>}
                </li>
              ))}
            {doctorIssues > 8 && (
              <li className="text-xs text-mute">… 还有 {doctorIssues - 8} 项，请到诊所查看</li>
            )}
          </ul>
        </div>
      )}

      {/* 快速导航 */}
      <div className="grid gap-2 sm:grid-cols-3">
        <NavCard title="Agent 诊断" desc="检测全部 Agent 状态" href="/clinic" sub="agent" />
        <NavCard title="任务面板" desc="查看工单与 FSM" href="/tasks" />
        <NavCard title="其它工具" desc="流水线/统计/告警" sub="进入其它面板" />
      </div>
    </div>
  );
}

// ── 子组件 ───────────────────────────────────────────────────────────
function IndicatorCard({
  label,
  value,
  ok,
  color,
}: {
  label: string;
  value: string;
  ok?: boolean;
  color: string;
}) {
  const statusDot = ok === true ? "bg-mint" : ok === false ? "bg-flare" : "bg-mute";
  return (
    <div className="rounded-sm border border-rail bg-hull/50 p-3 text-center">
      <p className="hud-label text-[10px]">{label}</p>
      <p className={`mt-1 text-lg font-display ${color}`}>
        <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1.5 align-middle ${statusDot}`} />
        {value}
      </p>
    </div>
  );
}

function NavCard({ title, desc, href, sub }: { title: string; desc: string; href?: string; sub?: string }) {
  return (
    <a
      href={href || "#"}
      className="rounded-sm border border-rail bg-hull/50 p-3 transition hover:border-cyan-signal/40 hover:shadow-glow no-underline"
      onClick={(e) => {
        if (!href) e.preventDefault();
      }}
    >
      <p className="font-display text-xs text-cyan-signal tracking-wide">{title}</p>
      <p className="mt-1 text-xs text-mute">{desc}</p>
      {sub && <p className="mt-0.5 text-[10px] text-mute">{sub}</p>}
    </a>
  );
}
