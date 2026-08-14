/**
 * Workflow：点卡片展开详情子卡，可编辑并保存
 */
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ErrorAlert } from "../../components/ErrorAlert";

type WfSummary = {
  id?: string;
  display?: string | { title?: string; zh?: string; en?: string };
  mode?: string;
  phase_count?: number;
  gate_count?: number;
  task_types?: string[];
  tags?: string[];
};

type Phase = {
  id?: string;
  name?: string;
  title?: string;
  agent?: string;
  display?: string | { zh?: string; en?: string; title?: string };
  steps?: unknown[];
};

type Gate = {
  gate_id?: string;
  id?: string;
  actor?: string;
  display?: string | { zh?: string; en?: string; title?: string };
  required_attachments_min?: number;
};

type WfDetail = {
  id?: string;
  version?: string;
  display?: unknown;
  mode?: string;
  phases?: Phase[];
  gates?: Gate[];
  task_types?: string[];
  tags?: string[];
  llm_policy?: Record<string, unknown>;
  [key: string]: unknown;
};

function labelOf(d: unknown, fallback = ""): string {
  if (typeof d === "string" && d.trim()) return d;
  if (d && typeof d === "object") {
    const o = d as { title?: string; zh?: string; en?: string; name?: string };
    return o.zh || o.title || o.en || o.name || fallback;
  }
  return fallback;
}

function displayName(w: { id?: string; display?: unknown }): string {
  return labelOf(w.display, w.id || "workflow");
}

function phaseLabel(ph: Phase, i: number): string {
  return labelOf(ph.display, ph.title || ph.name || ph.id || `P${i + 1}`);
}

function gateLabel(g: Gate, i: number): string {
  return labelOf(g.display, g.gate_id || g.id || `gate-${i + 1}`);
}

function cloneWf(w: WfDetail): WfDetail {
  return JSON.parse(JSON.stringify(w)) as WfDetail;
}

export function WorkflowBoardPage() {
  const [items, setItems] = useState<WfSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState<WfDetail | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draftId, setDraftId] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftPhases, setDraftPhases] = useState("intake,plan,build,verify");

  async function load() {
    setErr("");
    const r = await api<{ workflows?: WfSummary[] }>("/api/workflows");
    if (r.ok) setItems(r.data.workflows || []);
    else setErr(r.error);
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!activeId) {
      setDraft(null);
      return;
    }
    let cancelled = false;
    setLoadingId(activeId);
    setErr("");
    void (async () => {
      const r = await api<{ workflow?: WfDetail }>(`/api/workflows/${encodeURIComponent(activeId)}`);
      if (cancelled) return;
      setLoadingId(null);
      if (r.ok) {
        if (r.data.workflow) {
          setDraft(cloneWf(r.data.workflow));
        } else {
          setDraft(null);
          setErr("工作流不存在");
        }
      } else {
        setDraft(null);
        setErr(r.error || "加载工作流失败");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  function patchDraft(patch: Partial<WfDetail>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  function setDisplayZh(zh: string) {
    setDraft((d) => {
      if (!d) return d;
      const prev = d.display;
      const base =
        prev && typeof prev === "object" && !Array.isArray(prev)
          ? { ...(prev as Record<string, unknown>) }
          : typeof prev === "string"
            ? { title: prev }
            : {};
      return { ...d, display: { ...base, zh, title: zh } };
    });
  }

  async function saveDraft() {
    if (!draft?.id) return;
    setBusy(true);
    setMsg("");
    setErr("");
    const r = await api(`/api/workflows/${encodeURIComponent(draft.id)}`, {
      method: "POST",
      body: JSON.stringify({ workflow: draft }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已保存 ${draft.id}`);
      await load();
    } else setErr(r.error);
  }

  async function createWf() {
    const id = draftId.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_");
    if (!/^[a-z][a-z0-9_]{1,63}$/.test(id)) {
      setErr("id 需小写字母开头，仅 a-z0-9_");
      return;
    }
    const phaseIds = draftPhases
      .split(/[,，\s]+/)
      .map((x) => x.trim())
      .filter(Boolean);
    setBusy(true);
    setMsg("");
    const workflow: WfDetail = {
      id,
      version: "1.0.0",
      display: { zh: draftTitle.trim() || id, title: draftTitle.trim() || id },
      mode: "fixed_phases",
      task_types: [id],
      phases: phaseIds.map((pid) => ({ id: pid, display: { zh: pid } })),
      gates: [],
    };
    const r = await api(`/api/workflows/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ workflow }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已创建 ${id}`);
      setCreating(false);
      setDraftId("");
      setDraftTitle("");
      await load();
      setActiveId(id);
    } else setErr(r.error);
  }

  function updatePhase(i: number, patch: Partial<Phase>) {
    setDraft((d) => {
      if (!d) return d;
      const phases = [...(d.phases || [])];
      phases[i] = { ...phases[i], ...patch };
      return { ...d, phases };
    });
  }

  function updateGate(i: number, patch: Partial<Gate>) {
    setDraft((d) => {
      if (!d) return d;
      const gates = [...(d.gates || [])];
      gates[i] = { ...gates[i], ...patch };
      return { ...d, gates };
    });
  }

  function addPhase() {
    setDraft((d) => {
      if (!d) return d;
      const n = (d.phases || []).length + 1;
      return {
        ...d,
        phases: [...(d.phases || []), { id: `phase_${n}`, display: { zh: `阶段 ${n}` } }],
      };
    });
  }

  function removePhase(i: number) {
    setDraft((d) => {
      if (!d) return d;
      return { ...d, phases: (d.phases || []).filter((_, idx) => idx !== i) };
    });
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="soft-panel-title">工作流</p>
          <p className="soft-panel-sub">点卡片展开详情 · 可编辑保存</p>
        </div>
        <button type="button" className="hud-btn-amber" onClick={() => setCreating((v) => !v)}>
          {creating ? "取消" : "新建"}
        </button>
      </header>
      <ErrorAlert message={err} />
      {msg ? <p className="text-xs text-mint">{msg}</p> : null}

      {creating ? (
        <div className="soft-panel space-y-2">
          <label className="block">
            <span className="text-[11px] text-mute">id</span>
            <input
              className="hud-input mt-1 font-mono text-xs"
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
              placeholder="video_publish"
            />
          </label>
          <label className="block">
            <span className="text-[11px] text-mute">显示名</span>
            <input
              className="hud-input mt-1 text-xs"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              placeholder="视频发布"
            />
          </label>
          <label className="block">
            <span className="text-[11px] text-mute">阶段（逗号分隔）</span>
            <input
              className="hud-input mt-1 font-mono text-xs"
              value={draftPhases}
              onChange={(e) => setDraftPhases(e.target.value)}
            />
          </label>
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void createWf()}>
            创建并保存
          </button>
        </div>
      ) : null}

      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((w, idx) => {
          const id = String(w.id || "");
          const open = activeId === id;
          return (
            <li key={id || idx} className={`space-y-2 ${open ? "sm:col-span-2" : ""}`}>
              <button
                type="button"
                className={`agent-soft-tile min-h-[120px] w-full ${open ? "ring-1 ring-white/20" : ""}`}
                onClick={() => setActiveId(open ? null : id)}
                aria-expanded={open}
              >
                <p className="font-display text-[1rem] font-semibold tracking-[-0.02em] text-frost">
                  {displayName(w)}
                </p>
                <p className="font-mono text-[10px] text-mute">{w.id}</p>
                <div className="mt-auto flex flex-wrap gap-1.5">
                  <span className="agent-chip">{w.mode || "flow"}</span>
                  <span className="agent-chip">{w.phase_count ?? 0} 阶段</span>
                  <span className="agent-chip">{w.gate_count ?? 0} 门</span>
                  <span className="agent-chip">{open ? "收起" : "展开编辑"}</span>
                </div>
              </button>

              {open ? (
                <div className="soft-panel space-y-3" onClick={(e) => e.stopPropagation()}>
                  {loadingId === id || !draft || draft.id !== id ? (
                    <p className="text-sm text-mute">加载详情…</p>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="soft-panel-title">{displayName(draft)}</p>
                        <button
                          type="button"
                          className="hud-btn-amber"
                          disabled={busy}
                          onClick={() => void saveDraft()}
                        >
                          保存修改
                        </button>
                      </div>

                      <div className="grid gap-2 sm:grid-cols-2">
                        <label className="block">
                          <span className="text-[11px] text-mute">显示名 (zh)</span>
                          <input
                            className="hud-input mt-1 text-xs"
                            value={labelOf(draft.display)}
                            onChange={(e) => setDisplayZh(e.target.value)}
                          />
                        </label>
                        <label className="block">
                          <span className="text-[11px] text-mute">模式 mode</span>
                          <input
                            className="hud-input mt-1 font-mono text-xs"
                            value={draft.mode || ""}
                            onChange={(e) => patchDraft({ mode: e.target.value })}
                          />
                        </label>
                        <label className="block sm:col-span-2">
                          <span className="text-[11px] text-mute">任务类型 task_types（逗号分隔）</span>
                          <input
                            className="hud-input mt-1 font-mono text-xs"
                            value={(draft.task_types || []).join(", ")}
                            onChange={(e) =>
                              patchDraft({
                                task_types: e.target.value
                                  .split(/[,，\s]+/)
                                  .map((x) => x.trim())
                                  .filter(Boolean),
                              })
                            }
                          />
                        </label>
                        <label className="block sm:col-span-2">
                          <span className="text-[11px] text-mute">标签 tags（逗号分隔）</span>
                          <input
                            className="hud-input mt-1 font-mono text-xs"
                            value={(draft.tags || []).join(", ")}
                            onChange={(e) =>
                              patchDraft({
                                tags: e.target.value
                                  .split(/[,，\s]+/)
                                  .map((x) => x.trim())
                                  .filter(Boolean),
                              })
                            }
                          />
                        </label>
                      </div>

                      <div>
                        <div className="mb-2 flex items-center justify-between">
                          <p className="text-[11px] font-medium text-frost/80">阶段 phases</p>
                          <button type="button" className="hud-btn" onClick={addPhase}>
                            + 阶段
                          </button>
                        </div>
                        {(draft.phases || []).length === 0 ? (
                          <p className="text-sm text-mute">无阶段（如 llm_adaptive 可只靠门禁）</p>
                        ) : (
                          <>
                            <div className="wf-rail mb-3" aria-hidden>
                              {(draft.phases || []).map((ph, i) => (
                                <div
                                  key={String(ph.id || i)}
                                  className="wf-node"
                                  style={{ animationDelay: `${i * 0.1}s` }}
                                >
                                  <span className="wf-dot" />
                                  <span className="wf-label">{phaseLabel(ph, i)}</span>
                                  {i < (draft.phases || []).length - 1 ? <span className="wf-link" /> : null}
                                </div>
                              ))}
                            </div>
                            <ul className="space-y-2">
                              {(draft.phases || []).map((ph, i) => (
                                <li key={String(ph.id || i)} className="soft-inset space-y-2">
                                  <div className="flex flex-wrap gap-2">
                                    <label className="min-w-[7rem] flex-1">
                                      <span className="text-[10px] text-mute">id</span>
                                      <input
                                        className="hud-input mt-0.5 font-mono text-xs"
                                        value={ph.id || ""}
                                        onChange={(e) => updatePhase(i, { id: e.target.value })}
                                      />
                                    </label>
                                    <label className="min-w-[7rem] flex-1">
                                      <span className="text-[10px] text-mute">显示名</span>
                                      <input
                                        className="hud-input mt-0.5 text-xs"
                                        value={phaseLabel(ph, i)}
                                        onChange={(e) =>
                                          updatePhase(i, {
                                            display: { zh: e.target.value },
                                            title: e.target.value,
                                          })
                                        }
                                      />
                                    </label>
                                    <button
                                      type="button"
                                      className="hud-btn self-end text-flare"
                                      onClick={() => removePhase(i)}
                                    >
                                      删除
                                    </button>
                                  </div>
                                  {(ph.steps || []).length > 0 ? (
                                    <p className="font-mono text-[10px] text-mute">
                                      steps: {JSON.stringify(ph.steps)}
                                    </p>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          </>
                        )}
                      </div>

                      <div>
                        <p className="mb-2 text-[11px] font-medium text-frost/80">门禁 gates</p>
                        {(draft.gates || []).length === 0 ? (
                          <p className="text-sm text-mute">无门禁</p>
                        ) : (
                          <ul className="space-y-2">
                            {(draft.gates || []).map((g, i) => (
                              <li key={String(g.gate_id || g.id || i)} className="soft-inset grid gap-2 sm:grid-cols-3">
                                <label className="block">
                                  <span className="text-[10px] text-mute">gate_id</span>
                                  <input
                                    className="hud-input mt-0.5 font-mono text-xs"
                                    value={g.gate_id || g.id || ""}
                                    onChange={(e) => updateGate(i, { gate_id: e.target.value })}
                                  />
                                </label>
                                <label className="block">
                                  <span className="text-[10px] text-mute">显示名</span>
                                  <input
                                    className="hud-input mt-0.5 text-xs"
                                    value={gateLabel(g, i)}
                                    onChange={(e) => updateGate(i, { display: { zh: e.target.value } })}
                                  />
                                </label>
                                <label className="block">
                                  <span className="text-[10px] text-mute">actor</span>
                                  <input
                                    className="hud-input mt-0.5 font-mono text-xs"
                                    value={g.actor || ""}
                                    onChange={(e) => updateGate(i, { actor: e.target.value })}
                                  />
                                </label>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>

                      {draft.llm_policy ? (
                        <div>
                          <p className="mb-1 text-[11px] font-medium text-frost/80">llm_policy</p>
                          <pre className="soft-inset max-h-40 overflow-auto font-mono text-[10px] text-mute">
                            {JSON.stringify(draft.llm_policy, null, 2)}
                          </pre>
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
        {items.length === 0 ? <li className="text-sm text-mute">暂无 workflow，点「新建」</li> : null}
      </ul>
    </div>
  );
}
