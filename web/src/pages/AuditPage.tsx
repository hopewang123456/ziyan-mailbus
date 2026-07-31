import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function AuditPage() {
  const [stats, setStats] = useState<unknown>(null);
  const [pending, setPending] = useState<unknown>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    void Promise.all([
      api("/api/tasks/audit/stats"),
      api("/api/tasks/audit/pending"),
    ]).then(([s, p]) => {
      if (s.ok) setStats(s.data);
      else setErr(s.error);
      if (p.ok) setPending(p.data);
      else if (!s.ok) setErr(p.error);
    });
  }, []);

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Flight recorder</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">审计</h2>
      </header>
      {err && <p className="text-sm text-flare">{err}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="hud-label mb-2">stats</p>
          <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
            {stats ? JSON.stringify(stats, null, 2) : "…"}
          </pre>
        </div>
        <div>
          <p className="hud-label mb-2">pending</p>
          <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
            {pending ? JSON.stringify(pending, null, 2) : "…"}
          </pre>
        </div>
      </div>
    </div>
  );
}
