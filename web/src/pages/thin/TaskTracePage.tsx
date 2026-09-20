import { useEffect, useState } from "react";
import { ErrorAlert } from "../../components/ErrorAlert";
import { api } from "../../lib/api";

export type TraceEvent = { ts?: string; phase?: string; actor?: string; detail?: string; source?: string };
type TraceResp = { task_id?: string; status?: string; intent?: string; events?: TraceEvent[]; steps?: unknown[] };

/** E9 生命周期时序（可复用组件） */
export function TraceTimeline({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TraceResp | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setErr("");
      const r = await api<TraceResp>(`/api/tasks/trace?id=${encodeURIComponent(taskId)}`);
      if (cancelled) return;
      if (r.ok) setData(r.data);
      else setErr(r.error);
    })();
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  if (err) return <ErrorAlert message={err} />;
  if (!data) return <p className="text-[12px] text-mute">回放加载中…</p>;
  return (
    <div>
      <p className="mb-1 text-[11px] text-mute">
        {data.task_id} · {data.status} · {data.intent}
      </p>
      <ul className="max-h-72 space-y-0.5 overflow-auto font-mono text-[11px]">
        {(data.events || []).map((e, i) => (
          <li key={i} className="flex gap-2">
            <span className="shrink-0 text-mute">{String(e.ts || "").slice(5, 19)}</span>
            <span className="w-20 shrink-0 text-frost/80">{e.phase}</span>
            <span className="w-24 shrink-0 truncate text-mute">{e.actor}</span>
            <span className="min-w-0 text-frost/90">{e.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** E9 驾驶舱卡片：输入 task_id 回放 */
export function TaskTracePage() {
  const [input, setInput] = useState("");
  const [active, setActive] = useState("");

  return (
    <div className="space-y-3 p-1">
      <header>
        <p className="soft-panel-title">工单回放</p>
        <p className="soft-panel-sub font-mono text-[11px]">
          /api/tasks/trace · 建单→派工→投递→执行→回执→验收→归档
        </p>
      </header>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setActive(input.trim());
        }}
      >
        <input
          className="hud-input min-w-0 flex-1 font-mono text-xs"
          placeholder="task_id（如 demo-… / tpl-…）"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="hud-btn !px-3 text-xs" disabled={!input.trim()}>
          回放
        </button>
      </form>
      {active ? (
        <div className="soft-panel px-3 py-2">
          <TraceTimeline taskId={active} />
        </div>
      ) : (
        <p className="text-[12px] text-mute">CLI 等价：mailbus trace &lt;task_id&gt;</p>
      )}
    </div>
  );
}
