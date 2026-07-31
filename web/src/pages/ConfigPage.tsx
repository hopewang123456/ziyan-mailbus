import { useEffect, useState } from "react";
import { api, getToken, setToken } from "../lib/api";

type TokenInfo = {
  configured?: boolean;
  token_masked?: string;
  hint?: string;
};

type SectionMeta = { id?: string; label?: string; editable?: boolean } | string;
type SectionList = { sections?: SectionMeta[] };

function sectionId(s: SectionMeta): string {
  return typeof s === "string" ? s : String(s.id || "");
}

function sectionLabel(s: SectionMeta): string {
  if (typeof s === "string") return s;
  return String(s.label || s.id || "");
}

export function ConfigPage() {
  const [tokenInput, setTokenInput] = useState(getToken());
  const [info, setInfo] = useState<TokenInfo | null>(null);
  const [sections, setSections] = useState<SectionMeta[]>([]);
  const [section, setSection] = useState("");
  const [editor, setEditor] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [probeOut, setProbeOut] = useState<unknown>(null);

  async function refresh() {
    const [t, s] = await Promise.all([
      api<TokenInfo>("/api/config/mailbus-token"),
      api<SectionList>("/api/settings/sections"),
    ]);
    if (t.ok) setInfo(t.data);
    if (s.ok) setSections(s.data.sections || []);
  }

  useEffect(() => {
    void refresh();
  }, []);

  function saveLocal() {
    setToken(tokenInput.trim());
    setMsg("已写入本机 localStorage（跨机写请求会带 Bearer）");
  }

  async function rotate() {
    setBusy(true);
    setMsg("");
    const r = await api<{ token?: string }>("/api/config/mailbus-token", { method: "POST", body: "{}" });
    setBusy(false);
    if (r.ok && r.data.token) {
      setTokenInput(r.data.token);
      setToken(r.data.token);
      setMsg("已轮换：明文仅此一次，已保存到本机");
      void refresh();
    } else {
      setMsg(r.ok ? "rotate 无 token" : r.error);
    }
  }

  async function loadSection(name: string) {
    setSection(name);
    setMsg("");
    setProbeOut(null);
    const r = await api<Record<string, unknown>>(`/api/settings/section/${encodeURIComponent(name)}`);
    if (r.ok) {
      // Drop envelope fields so save can POST body as patch
      const { status: _s, error: _e, ...rest } = r.data;
      setEditor(JSON.stringify(Object.keys(rest).length ? rest : r.data, null, 2));
    } else {
      setMsg(r.error);
      setEditor("");
    }
  }

  async function saveSection() {
    if (!section) return;
    setBusy(true);
    setMsg("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(editor);
    } catch {
      setBusy(false);
      setMsg("JSON 解析失败");
      return;
    }
    // Backend: POST /api/settings/section/<name> (no do_PATCH)
    const body =
      typeof parsed === "object" && parsed && "patch" in (parsed as object)
        ? parsed
        : { patch: parsed };
    const r = await api(`/api/settings/section/${encodeURIComponent(section)}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已保存 section=${section}`);
      void loadSection(section);
    } else {
      setMsg(r.error);
    }
  }

  async function probeServices() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/settings/section/services/probe", {
      method: "POST",
      body: "{}",
    });
    setBusy(false);
    if (r.ok) {
      setProbeOut(r.data);
      setMsg("probe ok");
    } else {
      setMsg(r.error);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="hud-label">Configuration</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide text-frost">配置 / Token</h2>
        <p className="mt-2 text-sm text-mute">
          loopback 写操作可免 token；跨机需 Authorization: Bearer &lt;Mailbus Token&gt;。
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">Mailbus Token</p>
          <p className="mt-2 text-sm text-mute">
            服务端掩码：{info?.token_masked || "—"} · configured={String(!!info?.configured)}
          </p>
          <p className="mt-1 text-xs text-mute/80">{info?.hint}</p>
          <label className="mt-4 block">
            <span className="hud-label">本机 Bearer</span>
            <input
              className="hud-input mt-2 font-mono text-xs"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="粘贴或轮换后自动填入"
              autoComplete="off"
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="hud-btn" onClick={saveLocal}>
              保存本地
            </button>
            <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void rotate()}>
              轮换 Token
            </button>
          </div>
          {msg && <p className="mt-3 text-xs text-amber-signal">{msg}</p>}
        </div>

        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <p className="hud-label">Settings sections</p>
          <ul className="mt-3 max-h-64 space-y-1 overflow-auto text-sm">
            {sections.length === 0 && <li className="text-mute">无数据或 API 未就绪</li>}
            {sections.map((s) => {
              const id = sectionId(s);
              if (!id) return null;
              return (
                <li key={id}>
                  <button
                    type="button"
                    className={`w-full border-b border-rail/60 py-1.5 text-left font-mono text-xs transition-colors ${
                      section === id ? "text-frost" : "text-frost/70 hover:text-frost"
                    }`}
                    onClick={() => void loadSection(id)}
                  >
                    {sectionLabel(s)}
                    <span className="ml-2 text-mute">{id}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {section && (
        <div className="rounded-sm border border-rail bg-hull/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="hud-label">
              section / {section}
              <span className="ml-2 normal-case tracking-normal text-mute">
                GET → 编辑 → POST patch
              </span>
            </p>
            <div className="flex flex-wrap gap-2">
              {section === "services" && (
                <button
                  type="button"
                  className="hud-btn"
                  disabled={busy}
                  onClick={() => void probeServices()}
                >
                  Probe services
                </button>
              )}
              <button
                type="button"
                className="hud-btn-amber"
                disabled={busy}
                onClick={() => void saveSection()}
              >
                保存 PATCH
              </button>
            </div>
          </div>
          <textarea
            className="hud-input mt-3 min-h-[280px] font-mono text-xs"
            value={editor}
            onChange={(e) => setEditor(e.target.value)}
            spellCheck={false}
          />
          {probeOut != null && (
            <pre className="mt-3 max-h-40 overflow-auto text-xs text-mute">
              {JSON.stringify(probeOut, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
