import { useCallback, useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";
import { TraceTimeline } from "./thin/TaskTracePage";

type QueueItem = {
  id?: string;
  status?: string;
  type?: string;
  task_id?: string;
  title?: string;
  hint?: string;
  [k: string]: unknown;
};

type QueueResp = {
  items?: QueueItem[];
  total?: number;
  status?: string;
};

export function HumanQueuePage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [comments, setComments] = useState<Record<string, string>>({});
  const [extras, setExtras] = useState<Record<string, string>>({});
  const [traceFor, setTraceFor] = useState("");

  // E8 来源分组标签
  const SOURCE_LABELS: Record<string, string> = {
    station_vacancy: "工位空缺",
    push_budget: "push 预算熔断",
    a2a_input_required: "A2A 需人工输入",
    plan_approval: "方案审批",
    final_acceptance: "终验",
    owner_confirmation: "负责人确认",
    workflow_gate: "流程闸门",
  };

  const load = useCallback(async () => {
    setErr("");
    const r = await api<QueueResp>("/api/human-queue");
    if (r.ok) setItems(Array.isArray(r.data.items) ? r.data.items : []);
    else setErr(r.error);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(
    id: string,
    decision: "approved" | "denied",
    extra?: { agent?: string; station?: string },
  ) {
    setBusy(id);
    setMsg("");
    const comment = (comments[id] || "").trim();
    const r = await api(`/api/human-queue/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer: "dashboard",
        ...(comment ? { comment, reason: comment } : {}),
        ...(extra?.agent ? { agent: extra.agent } : {}),
        ...(extra?.station ? { station: extra.station } : {}),
      }),
    });
    setBusy("");
    if (r.ok) {
      setMsg(`${id} → ${decision}`);
      setComments((c) => {
        const n = { ...c };
        delete n[id];
        return n;
      });
      void load();
    } else {
      setMsg(r.error);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="hud-label">Airlock</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">人机队列</h2>
          <p className="mt-2 text-sm text-mute">POST /api/human-queue/&lt;id&gt;/resolve</p>
        </div>
        <button type="button" className="hud-btn" onClick={() => void load()}>
          刷新
        </button>
      </header>
      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      {items.length === 0 ? (
        <p className="text-sm text-mute">{err ? "—" : "暂无待办"}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((it) => {
            const id = String(it.id || "");
            if (!id) return null;
            const pending = (it.status || "pending") === "pending";
            return (
              <li key={id} className="soft-panel">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-xs text-frost">{id}</p>
                    <p className="mt-1 text-sm">
                      {String(it.title || it.hint || it.type || "item")}
                      {it.task_id ? (
                        <span className="ml-2 font-mono text-xs text-mute">task={String(it.task_id)}</span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-xs text-mute">
                      status={String(it.status || "—")} · type={String(it.type || "—")}
                      {it.source ? ` · 来源 ${SOURCE_LABELS[String(it.source)] || String(it.source)}` : ""}
                    </p>
                    {typeof it.reason === "string" && it.reason ? (
                      <p className="mt-1 max-w-xl text-xs leading-snug text-amber-signal/90">{it.reason}</p>
                    ) : null}
                  </div>
                </div>
                {pending && (
                  <div className="mt-3 space-y-2">
                    <input
                      className="hud-input text-xs"
                      placeholder="可选 comment / reason"
                      value={comments[id] || ""}
                      onChange={(e) => setComments((c) => ({ ...c, [id]: e.target.value }))}
                    />
                    {it.source === "station_vacancy" ? (
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            className="hud-btn"
                            disabled={busy === id}
                            onClick={() => void resolve(id, "approved")}
                          >
                            补员后重试
                          </button>
                          <button
                            type="button"
                            className="hud-btn-amber"
                            disabled={busy === id}
                            onClick={() => void resolve(id, "denied")}
                          >
                            挂起
                          </button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <input
                            className="hud-input w-36 text-xs"
                            placeholder="临时指名 agent id"
                            value={extras[`${id}:agent`] || ""}
                            onChange={(e) => setExtras((x) => ({ ...x, [`${id}:agent`]: e.target.value }))}
                          />
                          <button
                            type="button"
                            className="hud-btn !px-2 text-xs"
                            disabled={busy === id || !(extras[`${id}:agent`] || "").trim()}
                            onClick={() =>
                              void resolve(id, "approved", { agent: (extras[`${id}:agent`] || "").trim() })
                            }
                          >
                            指名派发
                          </button>
                          <input
                            className="hud-input w-36 text-xs"
                            placeholder="改派工位 id"
                            value={extras[`${id}:station`] || ""}
                            onChange={(e) => setExtras((x) => ({ ...x, [`${id}:station`]: e.target.value }))}
                          />
                          <button
                            type="button"
                            className="hud-btn !px-2 text-xs"
                            disabled={busy === id || !(extras[`${id}:station`] || "").trim()}
                            onClick={() =>
                              void resolve(id, "approved", { station: (extras[`${id}:station`] || "").trim() })
                            }
                          >
                            改派工位
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="hud-btn"
                          disabled={busy === id}
                          onClick={() => void resolve(id, "approved")}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="hud-btn-amber"
                          disabled={busy === id}
                          onClick={() => void resolve(id, "denied")}
                        >
                          Deny
                        </button>
                      </div>
                    )}
                    {it.task_id ? (
                      <button
                        type="button"
                        className="text-[11px] text-frost/70 underline-offset-2 hover:underline"
                        onClick={() => setTraceFor(traceFor === id ? "" : id)}
                      >
                        {traceFor === id ? "收起回放" : "回放该工单"}
                      </button>
                    ) : null}
                    {traceFor === id && it.task_id ? (
                      <div className="soft-inset px-3 py-2">
                        <TraceTimeline taskId={String(it.task_id)} />
                      </div>
                    ) : null}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
