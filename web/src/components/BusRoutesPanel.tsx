/**
 * 总线路由 / 端口 typed：mailbus_workflow · mailbus_chains · launch_ports
 */
import { useEffect, useState } from "react";
import { api, formatSettingsEffects } from "../lib/api";
import { ErrorAlert } from "./ErrorAlert";

type ChainTpl = {
  id?: string;
  default?: boolean;
  tags?: string[];
  steps?: { agent_role?: string; action?: string }[];
};

type PortItem = {
  id: string;
  name?: string;
  type?: string;
  port?: number | null;
  default_port?: number | null;
  ttyd_port?: number | null;
  default_ttyd_port?: number | null;
  port_label?: string;
  source?: string;
  group?: string;
  launch_url?: string;
};

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function unwrapData(body: unknown): Record<string, unknown> {
  const root = asObj(body);
  const inner = root.data;
  if (inner && typeof inner === "object" && !Array.isArray(inner)) return asObj(inner);
  const { status: _s, error: _e, section: _sec, ...rest } = root;
  return rest;
}

export function BusRoutesPanel() {
  const [tab, setTab] = useState<"workflow" | "chains" | "ports">("workflow");
  const [toolLive, setToolLive] = useState(false);
  const [gatesText, setGatesText] = useState("");
  const [budget, setBudget] = useState(30);
  const [templates, setTemplates] = useState<ChainTpl[]>([]);
  const [ports, setPorts] = useState<PortItem[]>([]);
  const [portDraft, setPortDraft] = useState<Record<string, string>>({});
  const [ttydDraft, setTtydDraft] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [wfCount, setWfCount] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    const [w, c, p, wf] = await Promise.all([
      api("/api/settings/section/mailbus_workflow"),
      api("/api/settings/section/mailbus_chains"),
      api("/api/settings/section/launch_ports"),
      api<{ workflows?: unknown[] }>("/api/workflows"),
    ]);
    if (w.ok) {
      const d = unwrapData(w.data);
      setToolLive(Boolean(d.tool_live));
      const gates = d.tool_live_gates;
      setGatesText(Array.isArray(gates) ? gates.map(String).join("\n") : "");
    } else setErr(w.error);
    if (c.ok) {
      const d = unwrapData(c.data);
      setBudget(Number(d.daily_budget_cny ?? 30));
      const tpls = d.templates;
      setTemplates(Array.isArray(tpls) ? (tpls as ChainTpl[]) : []);
    } else setErr((prev) => prev || c.error);
    if (p.ok) {
      const root = asObj(p.data);
      const agents = root.agents;
      setPorts(Array.isArray(agents) ? (agents as PortItem[]) : []);
      const n = asObj(root.notes);
      setNotes([n.priority, n.claude_sync].filter(Boolean).map(String).join(" · "));
      const draft: Record<string, string> = {};
      const ttyd: Record<string, string> = {};
      for (const it of Array.isArray(agents) ? (agents as PortItem[]) : []) {
        draft[it.id] = it.port != null ? String(it.port) : "";
        if (it.type === "codex") ttyd[it.id] = it.ttyd_port != null ? String(it.ttyd_port) : "";
      }
      setPortDraft(draft);
      setTtydDraft(ttyd);
    } else setErr((prev) => prev || p.error);
    if (wf.ok) {
      const list = (wf.data as { workflows?: unknown[] })?.workflows;
      setWfCount(Array.isArray(list) ? list.length : 0);
    } else {
      setWfCount(null);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function saveWorkflow() {
    setBusy(true);
    setMsg("");
    setErr("");
    const tool_live_gates = gatesText
      .split(/\r?\n|,/)
      .map((x) => x.trim())
      .filter(Boolean);
    const r = await api("/api/settings/section/mailbus_workflow", {
      method: "POST",
      body: JSON.stringify({ patch: { tool_live: toolLive, tool_live_gates } }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(formatSettingsEffects(r.data, "已保存 mailbus_workflow"));
      void load();
    } else setErr(r.error);
  }

  async function saveChains() {
    setBusy(true);
    setMsg("");
    setErr("");
    const r = await api("/api/settings/section/mailbus_chains", {
      method: "POST",
      body: JSON.stringify({
        patch: {
          daily_budget_cny: budget,
          templates,
        },
      }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(formatSettingsEffects(r.data, "已保存 mailbus_chains"));
      void load();
    } else setErr(r.error);
  }

  async function savePorts() {
    setBusy(true);
    setMsg("");
    setErr("");
    const updates = ports.map((it) => {
      const raw = (portDraft[it.id] ?? "").trim();
      const body: Record<string, unknown> = { agent_id: it.id };
      if (raw === "") body.reset = true;
      else body.port = Number.parseInt(raw, 10);
      if (it.type === "codex") {
        const t = (ttydDraft[it.id] ?? "").trim();
        if (t !== "") body.ttyd_port = Number.parseInt(t, 10);
      }
      return body;
    }).filter((u) => {
      if (u.reset) return true;
      const p = u.port;
      return typeof p === "number" && Number.isFinite(p);
    });
    const r = await api("/api/settings/section/launch_ports", {
      method: "POST",
      body: JSON.stringify({ updates }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(formatSettingsEffects(r.data, `已保存 launch_ports（${updates.length} 项）`));
      void load();
    } else setErr(r.error);
  }

  function addTemplate() {
    setTemplates((prev) => [
      ...prev,
      {
        id: `tpl-${prev.length + 1}`,
        default: prev.length === 0,
        tags: ["dev"],
        steps: [
          { agent_role: "dispatcher", action: "plan" },
          { agent_role: "executor", action: "implement" },
        ],
      },
    ]);
  }

  return (
    <div className="soft-panel space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="soft-panel-title">路由 / 端口</p>
          <p className="soft-panel-sub">workflow · chains · launch_ports</p>
        </div>
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["workflow", "Workflow"],
              ["chains", "链路"],
              ["ports", "端口"],
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

      {tab === "workflow" && (
        <div className="space-y-3">
          <p className="text-xs text-mute">
            tool_live：全局是否允许 workflow 真执行工具；gates 列表内 gate 批准后可打开任务级 live。
          </p>
          <div className="soft-inset text-xs text-mute">
            注册表：{wfCount == null ? "—" : `${wfCount} 个 workflow`}
            <span className="mx-1">·</span>
            阶段/门闸编辑在设置页总线 SoftFold「工作流注册表」或舰桥工作流面板（
            <code className="font-mono">/api/workflows</code>）。
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={toolLive} onChange={(e) => setToolLive(e.target.checked)} />
            tool_live（全局）
          </label>
          <label className="block">
            <span className="hud-label">tool_live_gates（每行一个 gate_id）</span>
            <textarea
              className="hud-input mt-1 min-h-[100px] w-full font-mono text-xs"
              value={gatesText}
              placeholder={"publish_go\ntest_gate"}
              onChange={(e) => setGatesText(e.target.value)}
            />
          </label>
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void saveWorkflow()}>
            保存 mailbus_workflow
          </button>
        </div>
      )}

      {tab === "chains" && (
        <div className="space-y-3">
          <label className="block max-w-xs">
            <span className="hud-label">daily_budget_cny</span>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              type="number"
              min={0}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value) || 0)}
            />
          </label>
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-mute">templates（简化编辑：id / 默认 / tags / steps 摘要）</p>
            <button type="button" className="hud-btn" onClick={addTemplate}>
              加模板
            </button>
          </div>
          {templates.length === 0 && (
            <p className="text-xs text-mute">暂无模板 — 可点「加模板」或保存空壳后从 chains.template 习惯迁移。</p>
          )}
          <ul className="space-y-2">
            {templates.map((tpl, idx) => (
              <li key={`${tpl.id}-${idx}`} className="soft-inset space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    className="hud-input w-40 font-mono text-xs"
                    value={String(tpl.id || "")}
                    onChange={(e) => {
                      const v = e.target.value;
                      setTemplates((prev) => prev.map((t, i) => (i === idx ? { ...t, id: v } : t)));
                    }}
                  />
                  <label className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={Boolean(tpl.default)}
                      onChange={(e) => {
                        const on = e.target.checked;
                        setTemplates((prev) =>
                          prev.map((t, i) => ({
                            ...t,
                            default: i === idx ? on : on ? false : t.default,
                          })),
                        );
                      }}
                    />
                    default
                  </label>
                  <button
                    type="button"
                    className="hud-btn-amber text-xs"
                    onClick={() => setTemplates((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    删
                  </button>
                </div>
                <label className="block">
                  <span className="hud-label">tags（逗号分隔）</span>
                  <input
                    className="hud-input mt-1 w-full font-mono text-xs"
                    value={(tpl.tags || []).join(", ")}
                    onChange={(e) => {
                      const tags = e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean);
                      setTemplates((prev) => prev.map((t, i) => (i === idx ? { ...t, tags } : t)));
                    }}
                  />
                </label>
                <label className="block">
                  <span className="hud-label">steps（每行 role:action）</span>
                  <textarea
                    className="hud-input mt-1 min-h-[64px] w-full font-mono text-xs"
                    value={(tpl.steps || [])
                      .map((s) => `${s.agent_role || ""}:${s.action || ""}`)
                      .join("\n")}
                    onChange={(e) => {
                      const steps = e.target.value
                        .split(/\r?\n/)
                        .map((line) => line.trim())
                        .filter(Boolean)
                        .map((line) => {
                          const [agent_role, ...rest] = line.split(":");
                          return { agent_role: (agent_role || "").trim(), action: rest.join(":").trim() };
                        });
                      setTemplates((prev) => prev.map((t, i) => (i === idx ? { ...t, steps } : t)));
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void saveChains()}>
            保存 mailbus_chains
          </button>
        </div>
      )}

      {tab === "ports" && (
        <div className="space-y-3">
          {notes && <p className="text-xs text-mute">{notes}</p>}
          <p className="text-xs text-mute">端口留空并保存 = 重置为默认表（launch-ports.json）。</p>
          <ul className="max-h-[420px] space-y-2 overflow-auto">
            {ports.length === 0 && <li className="text-mute">无带浏览器的 agent</li>}
            {ports.map((it) => (
              <li key={it.id} className="soft-inset grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
                <div className="min-w-0">
                  <p className="font-mono text-xs text-frost">{it.id}</p>
                  <p className="truncate text-[10px] text-mute">
                    {it.type} · {it.port_label || "port"} · src={it.source || "—"}
                    {it.default_port != null ? ` · default=${it.default_port}` : ""}
                  </p>
                </div>
                <label className="block">
                  <span className="hud-label">port</span>
                  <input
                    className="hud-input mt-1 w-24 font-mono text-xs"
                    value={portDraft[it.id] ?? ""}
                    onChange={(e) => setPortDraft((p) => ({ ...p, [it.id]: e.target.value }))}
                  />
                </label>
                {it.type === "codex" ? (
                  <label className="block">
                    <span className="hud-label">ttyd</span>
                    <input
                      className="hud-input mt-1 w-24 font-mono text-xs"
                      value={ttydDraft[it.id] ?? ""}
                      onChange={(e) => setTtydDraft((p) => ({ ...p, [it.id]: e.target.value }))}
                    />
                  </label>
                ) : (
                  <span />
                )}
              </li>
            ))}
          </ul>
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void savePorts()}>
            保存 launch_ports
          </button>
        </div>
      )}
    </div>
  );
}
