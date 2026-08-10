import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "../components/ErrorAlert";
import { ConfigPage } from "./ConfigPage";

type Status = {
  version?: string;
  status?: string;
  agents?: number;
  unread_messages?: number;
  total_messages?: number;
};

/** 首页船徽 → 指挥摘要 */
export function CommandBriefPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api<Status>("/api/status").then((r) => {
      if (r.ok) setStatus(r.data);
      else setErr(r.error);
    });
  }, []);

  async function heartbeat() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/heartbeat");
    setBusy(false);
    setMsg(r.ok ? "心跳已触发" : r.error);
  }

  async function sendPing() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/send-msg", {
      method: "POST",
      body: JSON.stringify({ text: "[舰桥] ping", channel: "default" }),
    });
    setBusy(false);
    setMsg(r.ok ? "已发送" : r.error);
  }

  return (
    <div className="space-y-4" data-surface="fleet">
      <header>
        <p className="hud-label">Command</p>
        <h2 className="mt-1 font-display text-xl text-frost">指挥摘要</h2>
        <p className="mt-1 text-sm text-mute">
          {status?.version || status?.status || "…"} · agents {status?.agents ?? "—"} · 未读{" "}
          {status?.unread_messages ?? "—"} / 消息 {status?.total_messages ?? "—"}
        </p>
      </header>
      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-mint">{msg}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void sendPing()}>
          发消息
        </button>
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void heartbeat()}>
          心跳
        </button>
      </div>
      <p className="text-xs text-mute">流水线 / Gate 请从「其它 → 流水线」进入，不占用指挥首页。</p>
      <ConfigPage variant="gear" />
    </div>
  );
}
