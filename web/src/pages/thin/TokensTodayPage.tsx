import { useEffect, useState } from "react";
import { ErrorAlert } from "../../components/ErrorAlert";
import { api } from "../../lib/api";

type Summary = {
  day?: string;
  calls?: number;
  est_tokens_total?: number;
  by_kind?: Record<string, number>;
  by_agent?: Record<string, number>;
  top_tasks?: { task_id: string; est_tokens: number }[];
  peak?: { minute?: string; est_tokens?: number };
  budget?: { daily_est_tokens?: number; exceeded?: boolean; used_pct?: number | null };
};

/** E3 token 台账今日视图 — 驾驶舱卡片（尖峰归因入口） */
export function TokensTodayPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [drill, setDrill] = useState<{ task_id: string; entries: unknown[] } | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setErr("");
      const r = await api<Summary>("/api/tokens/summary");
      if (cancelled) return;
      if (r.ok) setData(r.data);
      else setErr(r.error);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function openTask(taskId: string) {
    setErr("");
    const r = await api<{ entries?: unknown[] }>(`/api/tokens/summary?task=${encodeURIComponent(taskId)}`);
    if (r.ok) setDrill({ task_id: taskId, entries: r.data.entries || [] });
    else setErr(r.error);
  }

  const b = data?.budget || {};
  const kindEntries = Object.entries(data?.by_kind || {});
  const agentEntries = Object.entries(data?.by_agent || {}).slice(0, 6);

  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="soft-panel-title">今日 Token 台账</p>
        <p className="soft-panel-sub font-mono text-[11px]">/api/tokens/summary · 估算口径，回执 usage 为上报口径</p>
      </header>
      {err ? <ErrorAlert message={err} /> : null}
      {!data ? (
        <p className="text-sm text-mute">加载中…</p>
      ) : (
        <>
          <div className="soft-panel flex flex-wrap items-baseline gap-x-4 gap-y-1 px-3 py-2">
            <span className="text-lg font-semibold">{data.est_tokens_total ?? 0} tok</span>
            <span className="text-[11px] text-mute">{data.calls ?? 0} 次记账 · {data.day}</span>
            {b.daily_est_tokens ? (
              <span className={b.exceeded ? "text-[12px] text-flare" : "text-[12px] text-mint"}>
                日预算 {b.daily_est_tokens} · 已用 {b.used_pct ?? "-"}%{b.exceeded ? " · ⚠ 超预算" : ""}
              </span>
            ) : null}
            {data.peak?.minute ? (
              <span className="text-[11px] text-mute">尖峰 {data.peak.minute} · {data.peak.est_tokens} tok</span>
            ) : null}
          </div>

          {kindEntries.length > 0 ? (
            <div className="soft-panel px-3 py-2">
              <p className="mb-1 text-[11px] text-mute">按类型</p>
              <div className="flex flex-wrap gap-x-4 text-[12px]">
                {kindEntries.map(([k, v]) => (
                  <span key={k}>
                    {k}: <span className="font-medium">{v}</span>
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {agentEntries.length > 0 ? (
            <div className="soft-panel px-3 py-2">
              <p className="mb-1 text-[11px] text-mute">按 Agent（估算）</p>
              <div className="flex flex-wrap gap-x-4 text-[12px]">
                {agentEntries.map(([k, v]) => (
                  <span key={k}>
                    {k}: <span className="font-medium">{v}</span>
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {(data.top_tasks || []).length > 0 ? (
            <div className="soft-panel px-3 py-2">
              <p className="mb-1 text-[11px] text-mute">工单 Top5（点击下钻归因）</p>
              <ul className="space-y-0.5 text-[12px]">
                {(data.top_tasks || []).map((t) => (
                  <li key={t.task_id}>
                    <button type="button" className="font-mono text-frost underline-offset-2 hover:underline" onClick={() => void openTask(t.task_id)}>
                      {t.task_id}
                    </button>
                    : {t.est_tokens} tok
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {drill ? (
            <div className="soft-panel px-3 py-2">
              <p className="mb-1 text-[11px] text-mute">下钻: {drill.task_id}（{drill.entries.length} 条）</p>
              <ul className="max-h-56 space-y-0.5 overflow-auto font-mono text-[11px]">
                {drill.entries.map((e, i) => {
                  const r = (e ?? {}) as Record<string, unknown>;
                  return (
                    <li key={i}>
                      [{String(r.ts ?? "").slice(0, 19)}] {String(r.kind ?? "?")} · {String(r.agent ?? "?")} ·{" "}
                      {String((r.usage as Record<string, unknown> | undefined)?.total ?? r.est_tokens ?? 0)} tok（{String(r.source ?? "")}）
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
