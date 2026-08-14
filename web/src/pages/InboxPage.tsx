import { useEffect, useState } from "react";
import { ErrorAlert } from "../components/ErrorAlert";
import { api } from "../lib/api";

export function InboxPage() {
  const [replies, setReplies] = useState<unknown>(null);
  const [agent, setAgent] = useState("agent-a");
  const [inbox, setInbox] = useState<unknown>(null);
  const [err, setErr] = useState("");
  const [to, setTo] = useState("agent-a");
  const [content, setContent] = useState("");
  const [priority, setPriority] = useState("normal");
  const [msgType, setMsgType] = useState("notice");
  const [sendMsg, setSendMsg] = useState("");

  useEffect(() => {
    void api("/api/replies").then((r) => {
      if (r.ok) setReplies(r.data);
      else setErr(r.error);
    });
  }, []);

  async function loadInbox() {
    setErr("");
    const r = await api(`/api/inbox/${encodeURIComponent(agent)}`);
    if (r.ok) setInbox(r.data);
    else setErr(r.error);
  }

  async function sendMessage() {
    setErr("");
    setSendMsg("");
    const r = await api<{ status?: string; msg_id?: string }>("/api/send-msg", {
      method: "POST",
      body: JSON.stringify({ to, content, priority, type: msgType }),
    });
    if (r.ok) {
      setSendMsg(`已发送 ${r.data.msg_id ?? ""}`.trim());
      setContent("");
    } else setErr(r.error);
  }

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Comms</p>
        <h2 className="mt-1 font-display text-2xl tracking-[-0.02em]">Inbox</h2>
      </header>

      <section className="space-y-3 soft-panel">
        <p className="hud-label">发送 · POST /api/send-msg</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="hud-label">To</span>
            <input
              className="hud-input mt-1 w-40"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="hud-label">Priority</span>
            <select
              className="hud-input mt-1 w-28"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="low">low</option>
            </select>
          </label>
          <label className="block">
            <span className="hud-label">Type</span>
            <select
              className="hud-input mt-1 w-28"
              value={msgType}
              onChange={(e) => setMsgType(e.target.value)}
            >
              <option value="notice">notice</option>
              <option value="task">task</option>
              <option value="query">query</option>
            </select>
          </label>
        </div>
        <label className="block">
          <span className="hud-label">Content</span>
          <textarea
            className="hud-input mt-1 min-h-20 w-full"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="消息正文"
          />
        </label>
        <button
          type="button"
          className="hud-btn"
          disabled={!to.trim() || !content.trim()}
          onClick={() => void sendMessage()}
        >
          发送
        </button>
        {sendMsg && <p className="text-sm text-cyan-signal">{sendMsg}</p>}
      </section>

      <div className="flex flex-wrap items-end gap-2">
        <label className="block">
          <span className="hud-label">Agent</span>
          <input
            className="hud-input mt-1 w-48"
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
          />
        </label>
        <button type="button" className="hud-btn" onClick={() => void loadInbox()}>
          拉取 inbox
        </button>
      </div>
      <ErrorAlert message={err} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="hud-label mb-2">/api/replies</p>
          <pre className="max-h-80 overflow-auto soft-inset text-xs text-mute">
            {replies ? JSON.stringify(replies, null, 2) : "—"}
          </pre>
        </div>
        <div>
          <p className="hud-label mb-2">/api/inbox/…</p>
          <pre className="max-h-80 overflow-auto soft-inset text-xs text-mute">
            {inbox ? JSON.stringify(inbox, null, 2) : "选择 agent 后拉取"}
          </pre>
        </div>
      </div>
    </div>
  );
}
