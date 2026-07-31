import { useState } from "react";
import { api } from "../lib/api";

export function ClinicPage() {
  const [doctor, setDoctor] = useState<unknown>(null);
  const [tools, setTools] = useState<unknown>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function runDoctor() {
    setBusy(true);
    setErr("");
    const r = await api("/api/doctor");
    setBusy(false);
    if (r.ok) setDoctor(r.data);
    else setErr(r.error);
  }

  async function loadTools() {
    setErr("");
    const r = await api("/api/clinic/tools");
    if (r.ok) setTools(r.data);
    else setErr(r.error);
  }

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Medbay</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">诊所</h2>
      </header>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void runDoctor()}>
          Run doctor
        </button>
        <button type="button" className="hud-btn" onClick={() => void loadTools()}>
          Clinic tools
        </button>
      </div>
      {err && <p className="text-sm text-flare">{err}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
          {doctor ? JSON.stringify(doctor, null, 2) : "doctor —"}
        </pre>
        <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
          {tools ? JSON.stringify(tools, null, 2) : "tools —"}
        </pre>
      </div>
    </div>
  );
}
