import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";

/** AI 助手浮窗（P2 D10/D11）— 双舱可唤起：指标问答（语义层真值）+ 手册 RAG 问答。 */
type Msg = { role: "user" | "assistant"; text: string; citations?: Array<{ source_id?: string; title?: string }> };

export function AssistantWindow({ open, onClose }: { open: boolean; onClose(): void }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  async function ask() {
    const q = input.trim();
    if (!q || busy) return;
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    const r = await api<{ answer?: string; citations?: Array<{ source_id?: string; title?: string }> }>(
      "/api/assistant/ask",
      { method: "POST", body: JSON.stringify({ question: q }) },
    );
    setBusy(false);
    if (r.ok && r.data?.answer) {
      setMessages((m) => [...m, { role: "assistant", text: r.data!.answer || "", citations: r.data!.citations }]);
    } else {
      const detail = r.ok ? "empty answer" : ("error" in r ? String(r.error) : "error");
      setMessages((m) => [...m, { role: "assistant", text: `助手暂不可用：${detail}（检查 internal_llm 配置）` }]);
    }
  }

  if (!open) return null;
  return (
    <div className="fixed inset-y-0 right-0 z-[92] flex w-full max-w-md flex-col border-l border-rail bg-hull/95 shadow-2xl backdrop-blur">
      <header className="flex items-center justify-between border-b border-rail px-4 py-3">
        <div>
          <p className="hud-label">Assistant</p>
          <h3 className="mt-1 font-display text-base text-frost">AI 助手</h3>
        </div>
        <button type="button" className="rounded px-2 py-1 text-mute hover:text-frost" onClick={onClose}>
          ✕
        </button>
      </header>

      <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto px-4 py-3" data-testid="assistant-msgs">
        {messages.length === 0 && (
          <p className="soft-panel-sub text-xs text-mute">
            问系统状态（指标走语义层真值）、操作方法（RAG 手册）或架构问题。
            <br />例：「现在有多少活跃告警？」「发令窗口怎么用？」
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[88%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
              m.role === "user" ? "ml-auto bg-rail text-frost" : "bg-rail/40 text-mute"
            }`}
          >
            <div className="whitespace-pre-wrap">{m.text}</div>
            {m.citations && m.citations.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {m.citations.slice(0, 4).map((c, k) => (
                  <span key={k} className="rounded bg-hull px-1.5 py-0.5 font-mono text-[10px] text-mint/80">
                    {c.source_id}/{c.title}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="max-w-[88%] rounded-lg bg-rail/40 px-3 py-2 text-xs text-mute">思考中…</div>}
      </div>

      <div className="border-t border-rail px-4 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            className="min-w-0 flex-1 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost placeholder:text-mute/60 focus:border-mint/60 focus:outline-none"
            placeholder="问点什么…（Enter 发送）"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void ask()}
          />
          <button type="button" className="hud-btn text-xs disabled:opacity-40" disabled={busy || !input.trim()} onClick={() => void ask()}>
            问
          </button>
        </div>
      </div>
    </div>
  );
}
