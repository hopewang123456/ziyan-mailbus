import { useCallback, useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import {
  getManagerPending,
  postTaskFsm,
  type ManagerPendingItem,
} from "../lib/api";

const BUCKET_ZH: Record<string, string> = {
  plan_approval: "计划待批",
  acceptance: "待终验",
  coordination: "待协调",
};

const ACTION_ZH: Record<string, string> = {
  "approve-plan": "批准计划",
  "approve-join": "批准汇合",
  accept: "验收",
  rollback: "回退",
  skip: "跳过",
  cancel: "中止",
  continue: "继续",
  priority: "改优先级",
};

/** 每个建议动作对应的请求体（reason 统一记录来源） */
function actionBody(action: string): Record<string, unknown> {
  const base = { reason: "manager_desk" } as Record<string, unknown>;
  if (action === "approve-plan") return { ...base, decision: "approved" };
  if (action === "approve-join") return { ...base, reviewer: "manager" };
  if (action === "priority") {
    const raw = window.prompt("新优先级（数字，越大越低优先）", "50");
    if (raw === null) return {};
    const p = Number.parseInt(raw, 10);
    if (Number.isNaN(p)) return {};
    return { priority: p, reason: "manager_desk" };
  }
  return base;
}

export function ManagerDeskPage() {
  const [items, setItems] = useState<ManagerPendingItem[]>([]);
  const [counts, setCounts] = useState<{ plan_approval: number; acceptance: number; coordination: number }>({
    plan_approval: 0,
    acceptance: 0,
    coordination: 0,
  });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setErr("");
    const r = await getManagerPending();
    if (r.ok) {
      setItems(Array.isArray(r.data.items) ? r.data.items : []);
      if (r.data.counts) setCounts(r.data.counts);
    } else {
      setErr(r.error);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function act(item: ManagerPendingItem, action: string) {
    const id = String(item.task_id || "");
    if (!id) return;
    const body = actionBody(action);
    if (action === "priority" && Object.keys(body).length === 0) return;
    setBusy(`${id}:${action}`);
    setMsg("");
    const r = await postTaskFsm(id, action, body);
    setBusy("");
    if (r.ok) {
      setMsg(`${id} → ${ACTION_ZH[action] || action} 成功`);
      void load();
    } else {
      setMsg(r.error || `${action} 失败`);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="hud-label">Manager Desk</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">管理者协调台</h2>
          <p className="mt-2 text-sm text-mute">
            计划待批 {counts.plan_approval} · 待终验 {counts.acceptance} · 待协调 {counts.coordination} · 共{" "}
            {items.length}
          </p>
        </div>
        <button type="button" className="hud-btn" onClick={() => void load()}>
          刷新
        </button>
      </header>

      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      {items.length === 0 ? (
        <p className="text-sm text-mute">{err ? "—" : "暂无待你处理的工单"}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((it) => {
            const id = String(it.task_id || "");
            const bucket = it.bucket || "";
            const step = it.current_step || {};
            return (
              <li key={id} className="soft-panel">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-mono text-xs text-frost">{id}</p>
                      {bucket && (
                        <span className="rounded bg-hull px-1.5 py-0.5 text-[11px] text-amber-signal">
                          {BUCKET_ZH[bucket] || bucket}
                        </span>
                      )}
                      {it.priority !== undefined && it.priority !== null && (
                        <span className="rounded bg-hull px-1.5 py-0.5 text-[11px] text-mute">P-{it.priority}</span>
                      )}
                    </div>
                    <p className="mt-1 text-sm">{String(it.summary || "—")}</p>
                    <p className="mt-1 text-xs text-mute">
                      {it.fsm_reason === "join_gate_review" || it.fsm_substate === "await_join_review"
                        ? `并行汇合待审 · join_role=${String(it.join_pending?.join_role_type ?? "—")}`
                        : step.role_zh
                          ? `${step.role_zh} · ${step.to_agent || "?"}`
                          : `state=${String(it.fsm_state || "—")}`}
                      {it.fsm_substate ? ` · ${it.fsm_substate}` : ""}
                      {it.task_type ? ` · ${it.task_type}` : ""}
                    </p>
                  </div>
                </div>
                {(it.suggested_actions || []).length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(it.suggested_actions || []).map((a) => (
                      <button
                        key={a}
                        type="button"
                        className={
                          a === "cancel"
                            ? "hud-btn-amber"
                            : a === "approve-join" || a === "approve-plan"
                              ? "hud-btn hud-btn-primary"
                              : "hud-btn"
                        }
                        disabled={busy === `${id}:${a}`}
                        onClick={() => void act(it, a)}
                      >
                        {ACTION_ZH[a] || a}
                      </button>
                    ))}
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
