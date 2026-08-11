import { useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

type AuditStats = {
  total_tasks?: number;
  audited_tasks?: number;
  pending_audit_tasks?: number;
  pass_count?: number;
  fail_count?: number;
  warn_count?: number;
  pass_rate?: number;
  total_audit_entries?: number;
};

type AuditTask = {
  task_id?: string;
  id?: string;
  status?: string;
  summary?: string;
  title?: string;
  updated_at?: string;
  created_at?: string;
  [k: string]: unknown;
};

const STAT_KEYS: { key: keyof AuditStats; label: string }[] = [
  { key: "total_tasks", label: "总任务" },
  { key: "audited_tasks", label: "已审计" },
  { key: "pending_audit_tasks", label: "待审计" },
  { key: "pass_count", label: "通过" },
  { key: "fail_count", label: "失败" },
  { key: "warn_count", label: "警告" },
  { key: "pass_rate", label: "通过率 %" },
  { key: "total_audit_entries", label: "审计条目" },
];

function taskId(t: AuditTask): string {
  return String(t.task_id || t.id || "");
}

export function AuditPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [pending, setPending] = useState<AuditTask[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [err, setErr] = useState("");

  useEffect(() => {
    void Promise.all([
      api<AuditStats>("/api/tasks/audit/stats"),
      api<{ tasks?: AuditTask[]; count?: number }>("/api/tasks/audit/pending"),
    ]).then(([s, p]) => {
      if (s.ok) setStats(s.data);
      else setErr(s.error);
      if (p.ok) {
        setPending(Array.isArray(p.data.tasks) ? p.data.tasks : []);
        setPendingCount(p.data.count ?? 0);
      } else if (!s.ok) setErr(p.error);
    });
  }, []);

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Flight recorder</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">审计</h2>
      </header>
      <ErrorAlert message={err} />

      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">Stats</p>
        {!stats ? (
          <p className="mt-2 text-sm text-mute">加载中…</p>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {STAT_KEYS.map(({ key, label }) => {
              const val = stats[key];
              if (val == null) return null;
              const display = key === "pass_rate" ? Number(val).toFixed(1) : String(val);
              return (
                <div key={key} className="border border-rail/50 px-3 py-2">
                  <p className="hud-label text-[10px]">{label}</p>
                  <p className="mt-1 font-mono text-lg text-frost">{display}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">
          Pending audit <span className="text-mute">({pendingCount})</span>
        </p>
        {pending.length === 0 ? (
          <p className="mt-2 text-sm text-mute">无待审计任务</p>
        ) : (
          <div className="mt-3 max-h-[55vh] overflow-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-rail text-mute">
                  <th className="py-2 pr-3 font-normal">task_id</th>
                  <th className="py-2 pr-3 font-normal">status</th>
                  <th className="py-2 pr-3 font-normal">summary</th>
                  <th className="py-2 font-normal">updated</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((t) => {
                  const id = taskId(t);
                  return (
                    <tr key={id} className="border-b border-rail/40">
                      <td className="py-2 pr-3 font-mono text-frost">{id}</td>
                      <td className="py-2 pr-3 text-mute">{String(t.status || "")}</td>
                      <td className="max-w-xs truncate py-2 pr-3 text-mute">
                        {String(t.summary || t.title || "")}
                      </td>
                      <td className="py-2 text-mute">
                        {String(t.updated_at || t.created_at || "")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
