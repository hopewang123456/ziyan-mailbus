import { useState } from "react";
import { api } from "../lib/api";

type DiscoverReport = {
  status?: string;
  agents?: Array<{ id?: string; name?: string; enabled?: boolean }>;
  count?: number;
  [k: string]: unknown;
};

export function DiscoverPage() {
  const [report, setReport] = useState<DiscoverReport | null>(null);
  const [active, setActive] = useState<unknown>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function discover() {
    setBusy(true);
    setMsg("");
    const r = await api<DiscoverReport>("/api/discover");
    setBusy(false);
    if (r.ok) {
      setReport(r.data);
      setMsg("discover ok");
    } else {
      setMsg(r.error);
    }
  }

  async function loadActive() {
    const r = await api("/api/agents/active");
    if (r.ok) setActive(r.data);
    else setMsg(r.error);
  }

  async function enableAgent(id: string, enabled: boolean) {
    setBusy(true);
    const r = await api(`/api/agents/${encodeURIComponent(id)}/enable`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
    setBusy(false);
    setMsg(r.ok ? `${id} enable→${enabled}` : r.error);
    void loadActive();
  }

  const agents = Array.isArray(report?.agents) ? report!.agents! : [];

  return (
    <div className="space-y-6">
      <header>
        <p className="hud-label">Fleet</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">发现 / Enable</h2>
      </header>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void discover()}>
          Run discover
        </button>
        <button type="button" className="hud-btn" onClick={() => void loadActive()}>
          Active agents
        </button>
      </div>
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">Discover report</p>
          {agents.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {agents.map((a, i) => {
                const id = String(a.id || a.name || i);
                return (
                  <li
                    key={id}
                    className="flex items-center justify-between gap-2 border-b border-rail/50 py-2 text-sm"
                  >
                    <span className="font-mono text-xs">{id}</span>
                    <span className="flex gap-1">
                      <button
                        type="button"
                        className="hud-btn !px-2 !py-1"
                        disabled={busy}
                        onClick={() => void enableAgent(id, true)}
                      >
                        on
                      </button>
                      <button
                        type="button"
                        className="hud-btn-amber !px-2 !py-1"
                        disabled={busy}
                        onClick={() => void enableAgent(id, false)}
                      >
                        off
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <pre className="mt-3 max-h-72 overflow-auto text-xs text-mute">
              {report ? JSON.stringify(report, null, 2) : "尚未 discover"}
            </pre>
          )}
        </div>
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">/api/agents/active</p>
          <pre className="mt-3 max-h-72 overflow-auto text-xs text-mute">
            {active ? JSON.stringify(active, null, 2) : "—"}
          </pre>
        </div>
      </div>
    </div>
  );
}
