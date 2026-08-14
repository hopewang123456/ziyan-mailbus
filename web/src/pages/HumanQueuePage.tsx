import { useCallback, useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

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

  const load = useCallback(async () => {
    setErr("");
    const r = await api<QueueResp>("/api/human-queue");
    if (r.ok) setItems(Array.isArray(r.data.items) ? r.data.items : []);
    else setErr(r.error);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(id: string, decision: "approved" | "denied") {
    setBusy(id);
    setMsg("");
    const comment = (comments[id] || "").trim();
    const r = await api(`/api/human-queue/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer: "dashboard",
        ...(comment ? { comment, reason: comment } : {}),
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
                    </p>
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
