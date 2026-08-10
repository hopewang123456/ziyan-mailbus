import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "../components/ErrorAlert";

type Item = {
  name?: string;
  kind?: string;
  description?: string;
  actions?: string[];
};

export function IntegrationsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<unknown>(null);
  const [prompt, setPrompt] = useState("mailbus neon starship bridge, cyan lights");
  const [amUrl, setAmUrl] = useState("");
  const [envMsg, setEnvMsg] = useState("");

  async function load() {
    setBusy(true);
    setErr("");
    const r = await api<{ integrations?: Item[]; note?: string }>("/api/settings/integrations");
    setBusy(false);
    if (r.ok) {
      setItems(r.data.integrations || []);
      setMsg(r.data.note || "ok");
    } else setErr(r.error);
  }

  useEffect(() => {
    void load();
    void api<{
      groups?: Record<string, { key?: string; value?: string }[]>;
    }>("/api/settings/env").then((r) => {
      if (!r.ok) return;
      for (const entries of Object.values(r.data.groups || {})) {
        const hit = (entries || []).find((e) => e.key === "AGENTMEMORY_URL");
        if (hit && typeof hit.value === "string") {
          setAmUrl(hit.value);
          break;
        }
      }
    });
  }, []);

  async function saveAgentMemoryUrl() {
    setBusy(true);
    setEnvMsg("");
    const r = await api("/api/settings/env", {
      method: "POST",
      body: JSON.stringify({ vars: { AGENTMEMORY_URL: amUrl.trim() } }),
    });
    setBusy(false);
    setEnvMsg(r.ok ? "AgentMemory URL 已写入" : r.error);
  }

  async function reloadPlugins() {
    setBusy(true);
    const r = await api("/api/dev/reload", { method: "POST", body: "{}" });
    setBusy(false);
    if (r.ok) setMsg("plugins reloaded");
    else setErr(r.error);
    void load();
  }

  async function invoke(name: string, action: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    const params: Record<string, string> = {};
    if (action === "txt2img") params.prompt = prompt;
    const r = await api(`/api/settings/integrations/${encodeURIComponent(name)}/invoke`, {
      method: "POST",
      body: JSON.stringify({ action, params }),
    });
    setBusy(false);
    if (r.ok) {
      setLast(r.data);
      setMsg(`${name}/${action} ok`);
    } else {
      setErr(r.error);
      setLast(r);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="hud-label">Integrations</p>
        <h2 className="mt-1 font-display text-2xl text-frost">限界集成</h2>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          ComfyUI / n8n / AgentMemory 同级：可 probe / 轻量 invoke，不进编排主链。
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void load()}>
          刷新
        </button>
        <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void reloadPlugins()}>
          软 Reload 插件
        </button>
      </div>

      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">AgentMemory URL</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            className="hud-input min-w-[16rem] flex-1 font-mono text-xs"
            value={amUrl}
            onChange={(e) => setAmUrl(e.target.value)}
            placeholder="http://127.0.0.1:3111"
          />
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void saveAgentMemoryUrl()}>
            保存
          </button>
        </div>
        {envMsg && <p className="mt-2 text-xs text-amber-signal">{envMsg}</p>}
      </div>

      <label className="hud-panel block p-3">
        <span className="hud-label">Comfy txt2img prompt</span>
        <input
          className="hud-input mt-2"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
        />
      </label>

      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-mint">{msg}</p>}

      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((it) => (
          <li key={it.name} className="hud-panel scanline relative p-4">
            <p className="font-display text-xs tracking-wider text-cyan-signal">{it.name}</p>
            <p className="mt-1 text-[10px] uppercase tracking-widest text-mute">{it.kind}</p>
            <p className="mt-2 text-sm text-frost/80">{it.description}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(it.actions || ["probe"]).map((act) => (
                <button
                  key={act}
                  type="button"
                  className={act === "txt2img" ? "hud-btn-amber" : "hud-btn"}
                  disabled={busy || !it.name}
                  onClick={() => void invoke(it.name!, act)}
                >
                  {act}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>

      {last != null && (
        <pre className="hud-panel max-h-64 overflow-auto p-3 font-mono text-[10px] text-mute">
          {JSON.stringify(last, null, 2)}
        </pre>
      )}
    </div>
  );
}
