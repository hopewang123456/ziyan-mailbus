import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorAlert } from "../components/ErrorAlert";
import { SoftFold } from "../components/SoftFold";

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
  const [gwToken, setGwToken] = useState("");
  const [gwConfigured, setGwConfigured] = useState(false);
  const [envMsg, setEnvMsg] = useState("");
  const [pluginSpec, setPluginSpec] = useState("");
  const [plugins, setPlugins] = useState<string[]>([]);
  const [addOpen, setAddOpen] = useState(false);

  async function load() {
    setBusy(true);
    setErr("");
    const r = await api<{ integrations?: Item[]; note?: string }>("/api/settings/integrations");
    setBusy(false);
    if (r.ok) {
      setItems(r.data.integrations || []);
      setPlugins((r.data as { plugins?: string[] }).plugins || []);
      setMsg(r.data.note || "ok");
    } else setErr(r.error);
  }

  useEffect(() => {
    void load();
    void api<{
      groups?: Record<string, { key?: string; value?: string; configured?: boolean }[]>;
    }>("/api/settings/env").then((r) => {
      if (!r.ok) return;
      for (const entries of Object.values(r.data.groups || {})) {
        for (const e of entries || []) {
          if (e.key === "AGENTMEMORY_URL" && typeof e.value === "string") {
            setAmUrl(e.value);
          }
          if (e.key === "OPENCLAW_GATEWAY_TOKEN") {
            setGwConfigured(Boolean(e.configured));
          }
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

  async function saveGatewayToken() {
    setBusy(true);
    setEnvMsg("");
    const r = await api("/api/settings/env", {
      method: "POST",
      body: JSON.stringify({ vars: { OPENCLAW_GATEWAY_TOKEN: gwToken.trim() } }),
    });
    setBusy(false);
    if (r.ok) {
      setGwConfigured(true);
      setGwToken("");
      setEnvMsg("OpenClaw Gateway Token 已写入（浏览器入口将自动免密）");
    } else {
      setEnvMsg(r.error);
    }
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


  async function addPlugin() {
    const spec = pluginSpec.trim();
    if (!spec) return;
    setBusy(true);
    setEnvMsg("");
    const r = await api<{ plugins?: string[] }>("/api/settings/integrations", {
      method: "POST",
      body: JSON.stringify({ action: "add_plugin", spec }),
    });
    setBusy(false);
    if (r.ok) {
      setPluginSpec("");
      setPlugins(r.data.plugins || []);
      setEnvMsg(`已添加插件 ${spec}`);
      setAddOpen(false);
      void load();
    } else setEnvMsg(r.error);
  }

  async function removePlugin(spec: string) {
    setBusy(true);
    const r = await api<{ plugins?: string[] }>("/api/settings/integrations", {
      method: "POST",
      body: JSON.stringify({ action: "remove_plugin", spec }),
    });
    setBusy(false);
    if (r.ok) {
      setPlugins(r.data.plugins || []);
      void load();
    } else setEnvMsg(r.error);
  }

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Integrations</p>
        <h2 className="mt-1 font-display text-2xl text-frost">限界集成</h2>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          各区块默认收起 · ComfyUI / n8n / AgentMemory 同级 probe
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void load()}>
          刷新
        </button>
        <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void reloadPlugins()}>
          软 Reload 插件
        </button>
        <button
          type="button"
          className="hud-btn-amber"
          onClick={() => setAddOpen((v) => !v)}
        >
          {addOpen ? "取消添加" : "+ 添加新插件"}
        </button>
      </div>

      <ErrorAlert message={err} />
      {msg && <p className="text-xs text-mint">{msg}</p>}

      {addOpen ? (
        <div className="soft-panel space-y-3">
          <p className="soft-panel-title">添加新插件</p>
          <p className="soft-panel-sub">写入 config.integrations.plugins · 如 mypkg.plugin:register</p>
          <div className="flex flex-wrap gap-2">
            <input
              className="hud-input min-w-[16rem] flex-1 font-mono text-xs"
              value={pluginSpec}
              onChange={(e) => setPluginSpec(e.target.value)}
              placeholder="module.path:register_fn"
              autoFocus
            />
            <button
              type="button"
              className="hud-btn-amber"
              disabled={busy || !pluginSpec.trim()}
              onClick={() => void addPlugin()}
            >
              确认添加
            </button>
          </div>
        </div>
      ) : null}

      <SoftFold title="第三方集成插件" hint="已登记插件列表" defaultOpen={plugins.length > 0}>
        <div className="mb-2">
          <button type="button" className="hud-btn" onClick={() => setAddOpen(true)}>
            + 添加新插件
          </button>
        </div>
        {plugins.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {plugins.map((spec) => (
              <li key={spec} className="agent-chip flex items-center gap-2">
                <span className="font-mono">{spec}</span>
                <button type="button" className="text-flare" disabled={busy} onClick={() => void removePlugin(spec)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-mute">尚未登记第三方插件（内置 n8n / comfyui / gpu 仍可用）</p>
        )}
      </SoftFold>

      <SoftFold title="AgentMemory URL" hint="共享记忆服务地址">
        <div className="flex flex-wrap gap-2">
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
        {envMsg && <p className="text-xs text-amber-signal">{envMsg}</p>}
      </SoftFold>

      <SoftFold
        title="OpenClaw Gateway Token"
        hint={gwConfigured ? "已配置 · 浏览器入口可免密" : "未配置（默认 change-me）"}
      >
        <div className="flex flex-wrap gap-2">
          <input
            className="hud-input min-w-[16rem] flex-1 font-mono text-xs"
            type="password"
            value={gwToken}
            onChange={(e) => setGwToken(e.target.value)}
            placeholder="输入新 token（留空不更新）"
          />
          <button type="button" className="hud-btn-amber" disabled={busy || !gwToken.trim()} onClick={() => void saveGatewayToken()}>
            保存
          </button>
        </div>
      </SoftFold>

      <SoftFold title="Comfy txt2img" hint="调用内置 comfy 时的默认 prompt">
        <input
          className="hud-input"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
        />
      </SoftFold>

      <SoftFold title="内置集成" hint="n8n / comfyui / gpu · probe / invoke" defaultOpen>
        <ul className="grid gap-3 sm:grid-cols-2">
          {items.map((it) => (
            <li key={it.name} className="soft-inset relative">
              <p className="font-display text-xs tracking-[-0.02em] text-cyan-signal">{it.name}</p>
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
          <pre className="soft-inset max-h-64 overflow-auto font-mono text-[10px] text-mute">
            {JSON.stringify(last, null, 2)}
          </pre>
        )}
      </SoftFold>
    </div>
  );
}
