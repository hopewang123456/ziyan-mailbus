import { useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

type DoctorItem = {
  level: "ok" | "warn" | "fail";
  category: string;
  message: string;
  detail?: string;
};

type DoctorResp = {
  ok?: boolean;
  issues?: number;
  warnings?: number;
  items?: DoctorItem[];
};

type ClinicTool = {
  id: string;
  name?: string;
  description?: string;
  category?: string;
  readonly?: boolean;
};

type RunResult = {
  ok?: boolean;
  stdout?: string;
  stderr?: string;
  error?: string;
  tool_id?: string;
  tool_name?: string;
  returncode?: number;
  elapsed_seconds?: number;
};

type LocaleResp = {
  ok?: boolean;
  errors?: Record<string, string>;
  covered?: boolean;
};

const LEVEL_ORDER = ["fail", "warn", "ok"] as const;
const LEVEL_STYLE: Record<string, string> = {
  fail: "text-flare",
  warn: "text-amber-signal",
  ok: "text-mint",
};

export function ClinicPage() {
  const [doctor, setDoctor] = useState<DoctorResp | null>(null);
  const [tools, setTools] = useState<ClinicTool[]>([]);
  const [runResults, setRunResults] = useState<Record<string, RunResult>>({});
  const [running, setRunning] = useState<string>("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [locale, setLocale] = useState<LocaleResp | null>(null);

  async function runDoctor() {
    setBusy(true);
    setErr("");
    const r = await api<DoctorResp>("/api/doctor");
    setBusy(false);
    if (r.ok) setDoctor(r.data);
    else setErr(r.error);
  }

  async function loadTools() {
    setErr("");
    const r = await api<{ tools?: ClinicTool[] }>("/api/clinic/tools");
    if (r.ok) setTools(Array.isArray(r.data.tools) ? r.data.tools : []);
    else setErr(r.error);
  }

  async function loadLocale() {
    setErr("");
    const r = await api<LocaleResp>("/api/locale/errors");
    if (r.ok) setLocale(r.data);
    else setErr(r.error);
  }

  async function runTool(toolId: string) {
    setRunning(toolId);
    setErr("");
    const r = await api<RunResult>("/api/clinic/run", {
      method: "POST",
      body: JSON.stringify({ tool_id: toolId, preset_index: 0 }),
    });
    setRunning("");
    if (r.ok || r.data) {
      setRunResults((prev) => ({ ...prev, [toolId]: r.data as RunResult }));
    }
    if (!r.ok) setErr(r.error);
  }

  const grouped = LEVEL_ORDER.map((lvl) => ({
    level: lvl,
    items: (doctor?.items || []).filter((i) => i.level === lvl),
  })).filter((g) => g.items.length > 0);

  const localeEntries = Object.entries(locale?.errors || {}).sort(([a], [b]) => a.localeCompare(b));

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
        <button type="button" className="hud-btn" onClick={() => void loadLocale()}>
          错误码目录
        </button>
      </div>
      <ErrorAlert message={err} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">Doctor</p>
          {!doctor ? (
            <p className="mt-2 text-sm text-mute">点击 Run doctor 加载诊断</p>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap gap-3 text-xs">
                <span className={doctor.ok ? "text-mint" : "text-flare"}>
                  {doctor.ok ? "OK" : "ISSUES"}
                </span>
                <span className="text-flare">issues {doctor.issues ?? 0}</span>
                <span className="text-amber-signal">warnings {doctor.warnings ?? 0}</span>
              </div>
              <div className="mt-3 max-h-[55vh] space-y-3 overflow-auto">
                {grouped.length === 0 && (
                  <p className="text-sm text-mute">无诊断项</p>
                )}
                {grouped.map(({ level, items }) => (
                  <div key={level}>
                    <p className={`hud-label mb-1 uppercase ${LEVEL_STYLE[level]}`}>{level}</p>
                    <ul className="space-y-1">
                      {items.map((item, idx) => (
                        <li
                          key={`${level}-${idx}`}
                          className="border-b border-rail/40 px-1 py-1.5 text-xs"
                        >
                          <span className="text-mute">[{item.category}]</span>{" "}
                          <span className="text-frost">{item.message}</span>
                          {item.detail && (
                            <p className="mt-0.5 truncate font-mono text-mute">{item.detail}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">Clinic tools</p>
          {tools.length === 0 ? (
            <p className="mt-2 text-sm text-mute">点击 Clinic tools 加载</p>
          ) : (
            <ul className="mt-3 max-h-[55vh] space-y-2 overflow-auto">
              {tools.map((t) => {
                const result = runResults[t.id];
                return (
                  <li key={t.id} className="border border-rail/50 p-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-frost">{t.name || t.id}</p>
                        {t.description && (
                          <p className="mt-0.5 text-xs text-mute">{t.description}</p>
                        )}
                        <p className="mt-0.5 font-mono text-xs text-mute">{t.id}</p>
                      </div>
                      <button
                        type="button"
                        className="hud-btn shrink-0 text-xs"
                        disabled={running === t.id}
                        onClick={() => void runTool(t.id)}
                      >
                        {running === t.id ? "…" : "Run"}
                      </button>
                    </div>
                    {result && (
                      <div className="mt-2 border-t border-rail/40 pt-2 text-xs">
                        <p className={result.ok ? "text-mint" : "text-flare"}>
                          {result.ok ? "ok" : "failed"}
                          {result.returncode != null && ` · rc ${result.returncode}`}
                          {result.elapsed_seconds != null && ` · ${result.elapsed_seconds}s`}
                        </p>
                        {result.error && (
                          <p className="mt-1 text-flare">{result.error}</p>
                        )}
                        {result.stdout && (
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-mute">
                            {result.stdout}
                          </pre>
                        )}
                        {result.stderr && (
                          <pre className="mt-1 max-h-16 overflow-auto whitespace-pre-wrap text-amber-signal">
                            {result.stderr}
                          </pre>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {locale && (
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">错误码目录 (locale)</p>
          <p className="mt-1 text-xs text-mute">
            covered={String(locale.covered)} · {localeEntries.length} codes
          </p>
          <ul className="mt-3 max-h-64 space-y-1 overflow-auto font-mono text-xs">
            {localeEntries.map(([code, zh]) => (
              <li key={code} className="border-b border-rail/30 py-1">
                <span className="text-cyan-signal">{code}</span>
                <span className="text-mute"> — </span>
                <span className="text-frost">{zh}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
