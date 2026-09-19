import { useEffect, useState } from "react";
import { api } from "../lib/api";

type TraceResp = { active?: boolean; task_id?: string };

/**
 * E-wizard 演示模式横幅：demo 命名空间存在（<store>/demo/）时顶部提示，
 * 一键清除后消失。不遮挡交互（细条），与 AuthTokenBanner 同层。
 */
export function DemoModeBanner() {
  const [active, setActive] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const r = await api<TraceResp>("/api/demo/trace");
      if (cancelled) return;
      setActive(Boolean(r.ok && r.data?.active));
      setTaskId(r.data?.task_id || "");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!active) return null;

  async function clean() {
    setBusy(true);
    const r = await api("/api/demo/clean", { method: "POST" });
    setBusy(false);
    if (r.ok) {
      setActive(false);
      window.location.reload();
    }
  }

  return (
    <div className="pointer-events-auto fixed left-1/2 top-14 z-[89] flex w-[min(92vw,36rem)] -translate-x-1/2 items-center gap-2 rounded border border-sky-400/40 bg-hull/95 px-3 py-1.5 text-[12px] text-frost shadow">
      <span className="font-medium text-sky-300">演示模式</span>
      <span className="min-w-0 truncate text-mute">
        demo 数据隔离在 store/demo/{taskId ? ` · 最近 ${taskId}` : ""}，不影响真实 store
      </span>
      <button
        type="button"
        className="hud-btn ml-auto shrink-0 !px-2 !py-0.5 text-[11px]"
        disabled={busy}
        onClick={() => void clean()}
      >
        {busy ? "清除中…" : "清除演示数据"}
      </button>
    </div>
  );
}
