import { useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../lib/api";
import { DiscoverPage } from "./DiscoverPage";
import { ErrorAlert } from "../components/ErrorAlert";

type TokenInfo = {
  configured?: boolean;
  token_masked?: string;
  hint?: string;
};

type SectionMeta = { id?: string; label?: string; editable?: boolean } | string;

export type ConfigVariant = "agent" | "llm" | "bus" | "gear" | "full";

const AGENT_MODEL_SECTIONS = new Set([
  "smart_routing",
  "mailbus_internal_llm",
  "services",
]);
const AGENT_RUNTIME_SECTIONS = new Set([
  "agents",
  "frameworks",
  "mailbus_codex",
  "mailbus_claude",
]);
const BUS_SECTIONS = new Set([
  "launch_ports",
  "mailbus_workflow",
  "mailbus_automation",
  "mailbus_intake_bridge",
  "scheduler",
  "mailbus_chains",
]);

function sectionId(s: SectionMeta): string {
  return typeof s === "string" ? s : String(s.id || "");
}

function sectionLabel(s: SectionMeta): string {
  if (typeof s === "string") return s;
  return String(s.label || s.id || "");
}

function SectionEditor({
  title,
  allow,
  sections,
}: {
  title: string;
  allow: Set<string> | null;
  sections: SectionMeta[];
}) {
  const [section, setSection] = useState("");
  const [editor, setEditor] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [probeOut, setProbeOut] = useState<unknown>(null);

  const filtered = useMemo(() => {
    if (!allow) return sections;
    return sections.filter((s) => allow.has(sectionId(s)));
  }, [allow, sections]);

  async function loadSection(name: string) {
    setSection(name);
    setMsg("");
    setProbeOut(null);
    const r = await api<Record<string, unknown>>(`/api/settings/section/${encodeURIComponent(name)}`);
    if (r.ok) {
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
    } else setMsg(r.error);
  }

  async function probeServices() {
    setBusy(true);
    const r = await api("/api/settings/section/services/probe", { method: "POST", body: "{}" });
    setBusy(false);
    if (r.ok) {
      setProbeOut(r.data);
      setMsg("probe ok");
    } else setMsg(r.error);
  }

  return (
    <div className="space-y-3 rounded-sm border border-rail bg-hull/50 p-4">
      <p className="hud-label">{title}</p>
      <ul className="max-h-40 space-y-1 overflow-auto text-sm">
        {filtered.length === 0 && <li className="text-mute">无匹配 section</li>}
        {filtered.map((s) => {
          const id = sectionId(s);
          if (!id) return null;
          return (
            <li key={id}>
              <button
                type="button"
                className={`w-full border-b border-rail/60 py-1.5 text-left font-mono text-xs ${
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
      {section && (
        <>
          <div className="flex flex-wrap gap-2">
            {section === "services" && (
              <button type="button" className="hud-btn" disabled={busy} onClick={() => void probeServices()}>
                Probe
              </button>
            )}
            <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void saveSection()}>
              保存 PATCH
            </button>
          </div>
          <textarea
            className="hud-input mt-2 min-h-[200px] w-full font-mono text-xs"
            value={editor}
            onChange={(e) => setEditor(e.target.value)}
            spellCheck={false}
          />
          {msg && <p className="text-xs text-amber-signal">{msg}</p>}
          {probeOut != null && (
            <pre className="max-h-32 overflow-auto text-xs text-mute">{JSON.stringify(probeOut, null, 2)}</pre>
          )}
        </>
      )}
    </div>
  );
}

function AgentOpsPanel() {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [alignOut, setAlignOut] = useState<unknown>(null);
  const [agentId, setAgentId] = useState("");
  const [toFramework, setToFramework] = useState("claude_code");
  const [dryRun, setDryRun] = useState(true);

  async function align() {
    setBusy(true);
    setMsg("");
    const r = await api("/api/align", { method: "POST", body: "{}" });
    setBusy(false);
    if (r.ok) {
      setAlignOut(r.data);
      setMsg("align ok");
    } else setMsg(r.error);
  }

  async function transfer() {
    setBusy(true);
    setMsg("");
    const r = await api(`/api/agents/${encodeURIComponent(agentId)}/transfer`, {
      method: "POST",
      body: JSON.stringify({ to_framework: toFramework, dry_run: dryRun }),
    });
    setBusy(false);
    setMsg(r.ok ? "transfer ok" : r.error);
    if (r.ok) setAlignOut(r.data);
  }

  return (
    <div className="space-y-3 rounded-sm border border-rail bg-hull/50 p-4">
      <p className="hud-label">运维 · align / transfer</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void align()}>
          Align store
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="block">
          <span className="hud-label">agent_id</span>
          <input className="hud-input mt-1 w-36" value={agentId} onChange={(e) => setAgentId(e.target.value)} />
        </label>
        <label className="block">
          <span className="hud-label">to_framework</span>
          <input
            className="hud-input mt-1 w-36"
            value={toFramework}
            onChange={(e) => setToFramework(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-mute">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          dry_run
        </label>
        <button
          type="button"
          className="hud-btn"
          disabled={busy || !agentId || !toFramework}
          onClick={() => void transfer()}
        >
          Transfer
        </button>
      </div>
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
      {alignOut != null && (
        <pre className="max-h-40 overflow-auto text-xs text-mute">{JSON.stringify(alignOut, null, 2)}</pre>
      )}
      <DiscoverPage />
    </div>
  );
}

function BusExtras() {
  const [paths, setPaths] = useState<unknown>(null);
  const [perm, setPerm] = useState<unknown>(null);
  const [a2a, setA2a] = useState<unknown>(null);
  const [err, setErr] = useState("");
  const [editor, setEditor] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    const [p, pe, a] = await Promise.all([
      api("/api/settings/paths"),
      api("/api/permission"),
      api("/api/a2a/protocol"),
    ]);
    if (p.ok) setPaths(p.data);
    else setErr(p.error);
    if (pe.ok) {
      setPerm(pe.data);
      setEditor(JSON.stringify(pe.data, null, 2));
    }
    if (a.ok) setA2a(a.data);
  }

  useEffect(() => {
    void load();
  }, []);

  async function savePerm() {
    setBusy(true);
    setErr("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(editor);
    } catch {
      setBusy(false);
      setErr("permission JSON 无效");
      return;
    }
    const r = await api("/api/permission", { method: "POST", body: JSON.stringify(parsed) });
    setBusy(false);
    if (r.ok) {
      setPerm(r.data);
      void load();
    } else setErr(r.error);
  }

  return (
    <div className="space-y-3">
      <ErrorAlert message={err} />
      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">Vault / Compose 路径（只读）</p>
        <pre className="mt-2 max-h-48 overflow-auto text-xs text-mute">
          {paths == null ? "…" : JSON.stringify(paths, null, 2)}
        </pre>
      </div>
      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">权限 · /api/permission</p>
        <textarea
          className="hud-input mt-2 min-h-[160px] w-full font-mono text-xs"
          value={editor}
          onChange={(e) => setEditor(e.target.value)}
          spellCheck={false}
        />
        <button type="button" className="hud-btn-amber mt-2" disabled={busy} onClick={() => void savePerm()}>
          保存权限
        </button>
        {perm != null && (
          <p className="mt-2 text-xs text-mute">loaded · {Object.keys(perm as object).length} keys</p>
        )}
      </div>
      <div className="rounded-sm border border-rail bg-hull/50 p-4">
        <p className="hud-label">A2A protocol</p>
        <pre className="mt-2 max-h-40 overflow-auto text-xs text-mute">
          {a2a == null ? "…" : JSON.stringify(a2a, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function GearPanel() {
  const [tokenInput, setTokenInput] = useState(getToken());
  const [info, setInfo] = useState<TokenInfo | null>(null);
  const [apiBase, setApiBase] = useState(() => localStorage.getItem("mailbus.api.base") || "");
  const [refreshSec, setRefreshSec] = useState(() => localStorage.getItem("mailbus.refresh.sec") || "30");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api<TokenInfo>("/api/config/mailbus-token").then((t) => {
      if (t.ok) setInfo(t.data);
    });
  }, []);

  function saveLocal() {
    setToken(tokenInput.trim());
    localStorage.setItem("mailbus.api.base", apiBase.trim());
    localStorage.setItem("mailbus.refresh.sec", refreshSec.trim() || "30");
    setMsg("已写入本机 localStorage");
  }

  async function rotate() {
    setBusy(true);
    setMsg("");
    const r = await api<{ token?: string }>("/api/config/mailbus-token", { method: "POST", body: "{}" });
    setBusy(false);
    if (r.ok && r.data.token) {
      setTokenInput(r.data.token);
      setToken(r.data.token);
      setMsg("已轮换：明文仅此一次");
    } else setMsg(r.ok ? "rotate 无 token" : r.error);
  }

  return (
    <div className="space-y-4 rounded-sm border border-rail bg-hull/50 p-4">
      <p className="hud-label">齿轮 · API / Token</p>
      <p className="text-sm text-mute">
        服务端掩码：{info?.token_masked || "—"} · configured={String(!!info?.configured)}
      </p>
      <label className="block">
        <span className="hud-label">本机 Bearer</span>
        <input
          className="hud-input mt-1 w-full font-mono text-xs"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          autoComplete="off"
        />
      </label>
      <label className="block">
        <span className="hud-label">API Base（可选前缀）</span>
        <input
          className="hud-input mt-1 w-full font-mono text-xs"
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          placeholder="空=同源"
        />
      </label>
      <label className="block">
        <span className="hud-label">刷新间隔（秒）</span>
        <input
          className="hud-input mt-1 w-32 font-mono text-xs"
          value={refreshSec}
          onChange={(e) => setRefreshSec(e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="hud-btn" onClick={saveLocal}>
          保存本地
        </button>
        <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void rotate()}>
          轮换 Token
        </button>
      </div>
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
    </div>
  );
}

/** Settings surface for cockpit knobs + gear. Same APIs as legacy ConfigPage. */
export function ConfigPage({ variant = "full" }: { variant?: ConfigVariant }) {
  const [sections, setSections] = useState<SectionMeta[]>([]);
  const v: ConfigVariant = variant === "llm" ? "agent" : variant;

  useEffect(() => {
    void api<{ sections?: SectionMeta[] }>("/api/settings/sections").then((s) => {
      if (s.ok) setSections(s.data.sections || []);
    });
  }, []);

  if (v === "gear") {
    return (
      <div className="space-y-4">
        <header>
          <p className="hud-label">Gear</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">齿轮</h2>
        </header>
        <GearPanel />
      </div>
    );
  }

  if (v === "agent") {
    return (
      <div className="space-y-4">
        <header>
          <p className="hud-label">Agent</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">智能体</h2>
          <p className="mt-1 text-sm text-mute">左：模型配置 · 右：智能体配置 · 下：运维</p>
        </header>
        <div className="grid gap-4 lg:grid-cols-2">
          <SectionEditor title="模型配置" allow={AGENT_MODEL_SECTIONS} sections={sections} />
          <SectionEditor title="智能体配置" allow={AGENT_RUNTIME_SECTIONS} sections={sections} />
        </div>
        <AgentOpsPanel />
      </div>
    );
  }

  if (v === "bus") {
    return (
      <div className="space-y-4">
        <header>
          <p className="hud-label">Bus</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">总线</h2>
        </header>
        <SectionEditor title="总线 sections" allow={BUS_SECTIONS} sections={sections} />
        <BusExtras />
      </div>
    );
  }

  // full / legacy: token + all sections
  return (
    <div className="space-y-6">
      <header>
        <p className="hud-label">Configuration</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide text-frost">配置 / Token</h2>
      </header>
      <GearPanel />
      <SectionEditor title="全部 sections" allow={null} sections={sections} />
    </div>
  );
}
