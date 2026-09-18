/**
 * 总线运行段 typed 表单：scheduler · intake_bridge · automation.verify
 */
import { useEffect, useState } from "react";
import { api, formatSettingsEffects } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

type Job = {
  id?: string;
  enabled?: boolean;
  interval_seconds?: number;
  cron?: string;
  lock?: string;
  limit?: number;
  [k: string]: unknown;
};

type SchedData = {
  enabled?: boolean;
  tick_seconds?: number;
  jobs?: Job[];
};

type IntakeData = {
  enabled?: boolean;
  auto_spawn_analyze?: boolean;
  auto_spawn_content?: boolean;
  auto_spawn_solution?: boolean;
  score_hint_min_for_ui?: number;
  solution_tier_default?: string;
  await_plan_approval_on_solution?: boolean;
};

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function unwrap(body: unknown): Record<string, unknown> {
  const root = asObj(body);
  const inner = root.data;
  if (inner && typeof inner === "object" && !Array.isArray(inner)) return asObj(inner);
  const { status: _s, error: _e, section: _sec, ...rest } = root;
  return rest;
}

export function BusOpsPanel() {
  const [tab, setTab] = useState<"scheduler" | "intake" | "automation">("scheduler");
  const [sched, setSched] = useState<SchedData>({});
  const [intake, setIntake] = useState<IntakeData>({});
  const [autoVerify, setAutoVerify] = useState<Record<string, unknown>>({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    const [s, i, a] = await Promise.all([
      api("/api/settings/section/scheduler"),
      api("/api/settings/section/mailbus_intake_bridge"),
      api("/api/settings/section/mailbus_automation"),
    ]);
    if (s.ok) setSched(unwrap(s.data) as SchedData);
    else setErr(s.error);
    if (i.ok) setIntake(unwrap(i.data) as IntakeData);
    else setErr((prev) => prev || i.error);
    if (a.ok) {
      const raw = unwrap(a.data);
      setAutoVerify(asObj(raw.verify));
    } else setErr((prev) => prev || a.error);
  }

  useEffect(() => {
    void load();
  }, []);

  async function saveSection(section: string, patch: Record<string, unknown>) {
    setBusy(true);
    setMsg("");
    setErr("");
    const r = await api(`/api/settings/section/${section}`, {
      method: "POST",
      body: JSON.stringify({ patch }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(
        formatSettingsEffects(
          r.data,
          `已保存 ${section}${section === "scheduler" || section === "mailbus_intake_bridge" ? "（可能需重启）" : ""}`,
        ),
      );
      void load();
    } else setErr(r.error);
  }

  const jobs = Array.isArray(sched.jobs) ? sched.jobs : [];

  return (
    <div className="soft-panel space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="soft-panel-title">总线运行段</p>
          <p className="soft-panel-sub">scheduler · intake · automation</p>
        </div>
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["scheduler", "调度"],
              ["intake", "Intake"],
              ["automation", "自动化"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? "hud-btn hud-btn-primary" : "hud-btn"}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      {tab === "scheduler" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={sched.enabled !== false}
                onChange={(e) => setSched((p) => ({ ...p, enabled: e.target.checked }))}
              />
              scheduler.enabled
            </label>
            <label className="block">
              <span className="hud-label">tick_seconds</span>
              <input
                className="hud-input mt-1 w-24 font-mono text-xs"
                type="number"
                min={1}
                value={Number(sched.tick_seconds ?? 10)}
                onChange={(e) => setSched((p) => ({ ...p, tick_seconds: Number(e.target.value) || 10 }))}
              />
            </label>
          </div>
          <ul className="max-h-[360px] space-y-2 overflow-auto">
            {jobs.length === 0 && <li className="text-mute">无 jobs</li>}
            {jobs.map((job, idx) => (
              <li key={String(job.id || idx)} className="soft-inset grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                <label className="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={job.enabled !== false}
                    onChange={(e) => {
                      const next = jobs.map((j, i) => (i === idx ? { ...j, enabled: e.target.checked } : j));
                      setSched((p) => ({ ...p, jobs: next }));
                    }}
                  />
                  <span className="truncate font-mono text-frost">{String(job.id || `job-${idx}`)}</span>
                  {job.lock ? <span className="truncate text-[10px] text-mute">lock={String(job.lock)}</span> : null}
                </label>
                <label className="block">
                  <span className="hud-label">interval</span>
                  <input
                    className="hud-input mt-1 w-24 font-mono text-xs"
                    type="number"
                    min={0}
                    placeholder="秒"
                    value={job.interval_seconds ?? ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const next = jobs.map((j, i) => {
                        if (i !== idx) return j;
                        const copy = { ...j };
                        if (raw === "") delete copy.interval_seconds;
                        else copy.interval_seconds = Number(raw) || 0;
                        return copy;
                      });
                      setSched((p) => ({ ...p, jobs: next }));
                    }}
                  />
                </label>
                <label className="block">
                  <span className="hud-label">cron</span>
                  <input
                    className="hud-input mt-1 w-36 font-mono text-xs"
                    placeholder="可选"
                    value={String(job.cron ?? "")}
                    onChange={(e) => {
                      const next = jobs.map((j, i) => (i === idx ? { ...j, cron: e.target.value } : j));
                      setSched((p) => ({ ...p, jobs: next }));
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="hud-btn-amber"
            disabled={busy}
            onClick={() =>
              void saveSection("scheduler", {
                enabled: sched.enabled !== false,
                tick_seconds: Number(sched.tick_seconds ?? 10),
                jobs,
              })
            }
          >
            保存 scheduler
          </button>
        </div>
      )}

      {tab === "intake" && (
        <div className="space-y-3">
          {(
            [
              ["enabled", "启用 Intake Bridge"],
              ["auto_spawn_analyze", "自动拉起 analyze"],
              ["auto_spawn_content", "自动拉起 content"],
              ["auto_spawn_solution", "自动拉起 solution"],
              ["await_plan_approval_on_solution", "solution 需计划批准"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={Boolean(intake[key])}
                onChange={(e) => setIntake((p) => ({ ...p, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
          <label className="block max-w-xs">
            <span className="hud-label">score_hint_min_for_ui</span>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              type="number"
              value={Number(intake.score_hint_min_for_ui ?? 75)}
              onChange={(e) => setIntake((p) => ({ ...p, score_hint_min_for_ui: Number(e.target.value) || 0 }))}
            />
          </label>
          <label className="block max-w-xs">
            <span className="hud-label">solution_tier_default</span>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              value={String(intake.solution_tier_default ?? "M")}
              onChange={(e) => setIntake((p) => ({ ...p, solution_tier_default: e.target.value }))}
            />
          </label>
          <button
            type="button"
            className="hud-btn-amber"
            disabled={busy}
            onClick={() => void saveSection("mailbus_intake_bridge", { ...intake })}
          >
            保存 mailbus_intake_bridge
          </button>
        </div>
      )}

      {tab === "automation" && (
        <div className="space-y-3">
          <p className="text-xs text-mute">对应 mailbus_automation.verify（交付物校验边界）。</p>
          <label className="block">
            <span className="hud-label">deliverables_dir</span>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              value={String(autoVerify.deliverables_dir ?? "deliverables")}
              onChange={(e) => setAutoVerify((p) => ({ ...p, deliverables_dir: e.target.value }))}
            />
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={Boolean(autoVerify.strict)}
              onChange={(e) => setAutoVerify((p) => ({ ...p, strict: e.target.checked }))}
            />
            strict
          </label>
          <label className="block">
            <span className="hud-label">required_fields（逗号分隔）</span>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              value={
                Array.isArray(autoVerify.required_fields)
                  ? (autoVerify.required_fields as unknown[]).map(String).join(", ")
                  : String(autoVerify.required_fields ?? "")
              }
              onChange={(e) =>
                setAutoVerify((p) => ({
                  ...p,
                  required_fields: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                }))
              }
            />
          </label>
          <label className="block">
            <span className="hud-label">notes</span>
            <textarea
              className="hud-input mt-1 min-h-[64px] w-full font-mono text-xs"
              value={String(autoVerify.notes ?? "")}
              onChange={(e) => setAutoVerify((p) => ({ ...p, notes: e.target.value }))}
            />
          </label>
          <button
            type="button"
            className="hud-btn-amber"
            disabled={busy}
            onClick={() =>
              void saveSection("mailbus_automation", {
                verify: {
                  ...autoVerify,
                  version: autoVerify.version || "1.0.0",
                },
              })
            }
          >
            保存 mailbus_automation
          </button>
        </div>
      )}
    </div>
  );
}
