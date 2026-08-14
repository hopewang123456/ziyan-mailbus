import { useCallback, useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

type TaskRow = {
  task_id?: string;
  id?: string;
  status?: string;
  summary?: string;
  title?: string;
  [k: string]: unknown;
};

type TasksResp = { tasks?: TaskRow[]; count?: number; total?: number };

/** Actions wired in handlers_tasks.handle_task_fsm_action */
const FSM_ACTIONS = [
  "rollback",
  "skip",
  "cancel",
  "pause",
  "priority",
  "approve-plan",
  "accept",
  "continue",
] as const;

type FsmAction = (typeof FSM_ACTIONS)[number];

export function TasksPage() {
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const [detail, setDetail] = useState<unknown>(null);
  const [fsm, setFsm] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState("5");

  const load = useCallback(async () => {
    setErr("");
    const r = await api<TasksResp>("/api/tasks");
    if (r.ok) setTasks(Array.isArray(r.data.tasks) ? r.data.tasks : []);
    else setErr(r.error);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function taskId(t: TaskRow): string {
    return String(t.task_id || t.id || "");
  }

  async function selectTask(id: string) {
    setSelected(id);
    setDetail(null);
    setFsm(null);
    setMsg("");
    const [d, f] = await Promise.all([
      api(`/api/tasks/${encodeURIComponent(id)}`),
      api(`/api/tasks/${encodeURIComponent(id)}/fsm`),
    ]);
    if (d.ok) setDetail(d.data);
    else setMsg(d.error);
    if (f.ok) setFsm(f.data);
    else if (!d.ok) setMsg((m) => m || f.error);
  }

  async function runAction(action: FsmAction) {
    if (!selected) return;
    setBusy(true);
    setMsg("");
    const body: Record<string, unknown> = {};
    const rsn = reason.trim();
    if (rsn) body.reason = rsn;
    if (action === "priority") {
      const p = Number(priority);
      if (!Number.isFinite(p)) {
        setBusy(false);
        setMsg("priority 需为数字");
        return;
      }
      body.priority = p;
    }
    const r = await api(`/api/tasks/${encodeURIComponent(selected)}/fsm/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`${action} ok`);
      if (typeof r.data === "object" && r.data && "fsm" in (r.data as object)) {
        setFsm(r.data);
      }
      void selectTask(selected);
      void load();
    } else {
      setMsg(r.error);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="hud-label">Mission board</p>
          <h2 className="mt-1 font-display text-2xl tracking-[-0.02em]">任务</h2>
        </div>
        <button type="button" className="hud-btn" onClick={() => void load()}>
          刷新
        </button>
      </header>
      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="soft-panel">
          <p className="hud-label">/api/tasks</p>
          <ul className="mt-3 max-h-[60vh] space-y-1 overflow-auto">
            {tasks.length === 0 && <li className="text-sm text-mute">无任务</li>}
            {tasks.map((t) => {
              const id = taskId(t);
              if (!id) return null;
              const active = selected === id;
              return (
                <li key={id}>
                  <button
                    type="button"
                    className={`w-full soft-list-btn !w-full text-left text-sm transition-colors ${
                      active ? "bg-[rgba(61,224,255,0.1)] text-frost" : "text-mute hover:text-frost"
                    }`}
                    onClick={() => void selectTask(id)}
                  >
                    <span className="font-mono text-xs">{id}</span>
                    <span className="ml-2 text-xs opacity-70">{String(t.status || "")}</span>
                    <p className="mt-0.5 truncate text-xs">
                      {String(t.summary || t.title || "")}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="space-y-4">
          <div className="soft-panel">
            <p className="hud-label">FSM 操作</p>
            {!selected ? (
              <p className="mt-2 text-sm text-mute">点左侧任务加载详情</p>
            ) : (
              <>
                <p className="mt-2 font-mono text-xs text-frost">{selected}</p>
                <label className="mt-3 block">
                  <span className="hud-label">reason（可选）</span>
                  <input
                    className="hud-input mt-1 text-xs"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="操作原因"
                  />
                </label>
                <label className="mt-2 block">
                  <span className="hud-label">priority 值</span>
                  <input
                    className="hud-input mt-1 text-xs"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    placeholder="仅 priority 动作使用"
                  />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  {FSM_ACTIONS.map((a) => (
                    <button
                      key={a}
                      type="button"
                      className={a === "cancel" ? "hud-btn-amber" : "hud-btn"}
                      disabled={busy}
                      onClick={() => void runAction(a)}
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="soft-panel">
            <p className="hud-label">/fsm</p>
            <pre className="mt-2 max-h-40 overflow-auto text-xs text-mute">
              {fsm ? JSON.stringify(fsm, null, 2) : "—"}
            </pre>
          </div>

          <div className="soft-panel">
            <p className="hud-label">task detail</p>
            <pre className="mt-2 max-h-48 overflow-auto text-xs text-mute">
              {detail ? JSON.stringify(detail, null, 2) : "—"}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
