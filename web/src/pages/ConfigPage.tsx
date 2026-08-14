import { useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "../lib/api";
import { DiscoverPage } from "./DiscoverPage";
import { ErrorAlert } from "../components/ErrorAlert";
import { ModelConfigPanel } from "../components/ModelConfigPanel";
import { AgentRuntimePanel } from "../components/AgentInstancePanel";
import { AssetPathsPanel } from "../components/AssetPathsPanel";
import { BusExtrasPanel } from "../components/BusExtrasPanel";
import { SoftFold } from "../components/SoftFold";

type TokenInfo = {
  configured?: boolean;
  token_masked?: string;
  hint?: string;
};

type SectionMeta = { id?: string; label?: string; editable?: boolean } | string;

export type ConfigVariant = "agent" | "llm" | "bus" | "gear" | "full";

const BUS_SECTIONS = new Set([
  "launch_ports",
  "mailbus_workflow",
  "mailbus_automation",
  "mailbus_intake_bridge",
  "scheduler",
  "mailbus_chains",
]);
const AGENT_RUNTIME_OTHER_SECTIONS = new Set(["frameworks", "mailbus_codex", "mailbus_claude"]);

function sectionId(s: SectionMeta): string {
  return typeof s === "string" ? s : String(s.id || "");
}

function sectionLabel(s: SectionMeta): string {
  if (typeof s === "string") return s;
  return String(s.label || s.id || "");
}

function flattenObj(obj: unknown, prefix = ""): { key: string; value: string }[] {
  const out: { key: string; value: string }[] = [];
  if (obj == null || typeof obj !== "object") {
    if (prefix) out.push({ key: prefix, value: obj == null ? "" : String(obj) });
    return out;
  }
  if (Array.isArray(obj)) {
    out.push({ key: prefix || "list", value: JSON.stringify(obj) });
    return out;
  }
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (k === "status" || k === "error" || k === "section") continue;
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) out.push(...flattenObj(v, key));
    else if (Array.isArray(v)) out.push({ key, value: JSON.stringify(v) });
    else out.push({ key, value: v == null ? "" : String(v) });
  }
  return out;
}

function unflattenObj(rows: { key: string; value: string }[]): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  for (const { key, value } of rows) {
    const parts = key.split(".").filter(Boolean);
    if (!parts.length) continue;
    let cur: Record<string, unknown> = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      if (!(p in cur) || typeof cur[p] !== "object" || cur[p] == null || Array.isArray(cur[p])) {
        cur[p] = {};
      }
      cur = cur[p] as Record<string, unknown>;
    }
    const leaf = parts[parts.length - 1];
    const trimmed = value.trim();
    if (trimmed === "true") cur[leaf] = true;
    else if (trimmed === "false") cur[leaf] = false;
    else if (trimmed !== "" && !Number.isNaN(Number(trimmed)) && /^-?\d+(\.\d+)?$/.test(trimmed)) {
      cur[leaf] = Number(trimmed);
    } else if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try {
        cur[leaf] = JSON.parse(trimmed);
      } catch {
        cur[leaf] = value;
      }
    } else cur[leaf] = value;
  }
  return root;
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
  const [rows, setRows] = useState<{ key: string; value: string }[]>([]);
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
      const { status: _s, error: _e, section: _sec, ...rest } = r.data;
      const payload = Object.keys(rest).length ? rest : r.data;
      setRows(flattenObj(payload));
    } else {
      setMsg(r.error);
      setRows([]);
    }
  }

  async function saveSection() {
    if (!section) return;
    setBusy(true);
    setMsg("");
    const parsed = unflattenObj(rows);
    const r = await api(`/api/settings/section/${encodeURIComponent(section)}`, {
      method: "POST",
      body: JSON.stringify({ patch: parsed }),
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
    <div className="soft-panel space-y-3">
      <p className="soft-panel-title">{title}</p>
      <ul className="max-h-48 space-y-1 overflow-auto">
        {filtered.length === 0 && <li className="px-2 text-sm text-mute">无匹配 section</li>}
        {filtered.map((s) => {
          const id = sectionId(s);
          if (!id) return null;
          return (
            <li key={id}>
              <button
                type="button"
                className={`soft-list-btn ${section === id ? "is-active" : ""}`}
                onClick={() => void loadSection(id)}
              >
                {sectionLabel(s)}
                <span className="ml-2 opacity-50">{id}</span>
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
              保存
            </button>
          </div>
          <div className="max-h-[420px] space-y-2 overflow-auto">
            {rows.length === 0 ? (
              <p className="text-sm text-mute">空配置</p>
            ) : (
              rows.map((row, idx) => (
                <label key={`${row.key}-${idx}`} className="block soft-inset">
                  <span className="font-mono text-[10px] text-mute">{row.key}</span>
                  <input
                    className="hud-input mt-1 font-mono text-xs"
                    value={row.value}
                    onChange={(e) => {
                      const v = e.target.value;
                      setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, value: v } : r)));
                    }}
                  />
                </label>
              ))
            )}
          </div>
          {msg && <p className="text-xs text-amber-signal">{msg}</p>}
          {probeOut != null && (
            <div className="soft-inset text-xs text-mute">
              {flattenObj(probeOut).map((r) => (
                <p key={r.key}>
                  <span className="text-frost/70">{r.key}</span>: {r.value}
                </p>
              ))}
            </div>
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
    <div className="soft-panel space-y-3">
      <p className="soft-panel-title">运维</p>
      <p className="soft-panel-sub">align / transfer / 发现</p>
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

function SkillsSourcePanel() {
  const [idx, setIdx] = useState<{
    agents?: Record<string, { framework?: string; archetype?: string; skills?: unknown[] }>;
    reverse?: Record<string, string[]>;
    orphans?: Array<{ id?: string; name?: string; layer?: string }>;
    updated_at?: string;
    source?: string;
  } | null>(null);
  const [paths, setPaths] = useState<Record<string, string> | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setErr("");
    const [r1, r2] = await Promise.all([
      api<{ index?: unknown }>("/api/skills/index"),
      api<{ paths?: Record<string, string> }>("/api/settings/paths"),
    ]);
    setBusy(false);
    if (r1.ok) setIdx((r1.data.index as typeof idx) ?? null);
    else setErr(r1.error);
    if (r2.ok) setPaths(r2.data.paths ?? null);
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="soft-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="soft-panel-title">技能源</p>
          <p className="soft-panel-sub">Obsidian SoT · 资产路径</p>
        </div>
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void load()}>
          重建索引
        </button>
      </div>
      <p className="mt-3 text-[13px] leading-relaxed text-mute">
        技能/规则声明 SoT 在 Obsidian 人物索引 frontmatter。资产根可由 env（MAILBUS_SKILLS_ROOT /
        MAILBUS_RULES_ROOT / MAILBUS_IDENTITIES_ROOT）覆盖。
      </p>
      {err && <ErrorAlert message={err} />}
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="soft-inset min-w-0">
          <p className="text-[11px] font-medium text-frost/70">资产路径</p>
          <pre className="mt-2 max-h-40 overflow-auto font-mono text-[10px] text-mute">
            {paths == null
              ? "…"
              : Object.entries(paths)
                  .filter(([k]) => /root|workspace|_dir/.test(k))
                  .map(([k, v]) => `${k} = ${v}`)
                  .join("\n")}
          </pre>
        </div>
        <div className="soft-inset min-w-0">
          <p className="text-[11px] font-medium text-frost/70">
            skills-index {idx?.updated_at ? `· ${idx.updated_at}` : ""}
          </p>
          <p className="mt-1 text-[10px] text-mute">
            {idx?.source || "…"} · {Object.keys(idx?.agents || {}).length} agents ·{" "}
            {Object.keys(idx?.reverse || {}).length} skills · {idx?.orphans?.length || 0} orphans
          </p>
        </div>
      </div>
      {idx && Object.keys(idx.agents || {}).length > 0 && (
        <div className="mt-3">
          <details className="soft-details">
            <summary>人物 → 技能 明细</summary>
            <div className="mt-2 max-h-72 overflow-auto">
              {Object.entries(idx.agents || {}).map(([aid, a]) => (
                <div key={aid} className="border-b border-white/[0.05] py-2 text-[11px]">
                  <span className="font-mono text-frost">{aid}</span>
                  <span className="ml-2 text-mute">{a.framework} / {a.archetype}</span>
                  <ul className="ml-4 mt-1 list-disc pl-4 text-mute">
                    {(a.skills || []).map((s, i) => {
                      const spec = s as { type?: string; id?: string; path?: string };
                      return <li key={i}>{spec.type}:{spec.id} <span className="opacity-50">{spec.path || ""}</span></li>;
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
      {idx && Object.keys(idx.orphans || {}).length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-medium text-amber-signal">孤儿技能（未被人物引用）</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {(idx.orphans || []).map((o) => (
              <li key={o.id || o.name} className="agent-chip agent-chip-warn">
                {o.id || o.name} · {o.layer}
              </li>
            ))}
          </ul>
        </div>
      )}
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
    <div className="soft-panel space-y-4">
      <div>
        <p className="soft-panel-title">API / Token</p>
        <p className="soft-panel-sub">
          服务端掩码：{info?.token_masked || "—"} · configured={String(!!info?.configured)}
        </p>
      </div>
      <p className="text-[13px] leading-relaxed text-mute">
        <span className="text-amber-signal">提示</span>：前端在 Windows 访问 WSL/Docker 后端时，跨机写操作
        需 Bearer token。Token 存在后端 <code className="font-mono">store/secrets.json</code>（或
        <code className="font-mono">MAILBUS_API_TOKEN</code> 环境变量）。获取方式：容器内
        <code className="font-mono">docker exec &lt;容器&gt; cat store/secrets.json</code>，
        或点下方「轮换 Token」（明文仅返回一次）。填好后保存即可，所有请求自动携带 Bearer。
      </p>
      <label className="block">
        <span className="hud-label">Bearer Token</span>
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
          <p className="mt-1 text-sm text-mute">点开折叠项编辑，默认收起</p>
        </header>
        <SoftFold title="API / Token" hint="mailbus 访问令牌">
          <GearPanel />
        </SoftFold>
      </div>
    );
  }

  if (v === "agent") {
    return (
      <div className="space-y-4">
        <header>
          <p className="hud-label">Agent</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">智能体</h2>
          <p className="mt-1 text-sm text-mute">各区块默认收起 · 点标题展开</p>
        </header>
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="space-y-3">
            <SoftFold title="模型 Provider" hint="API Key / Base URL">
              <ModelConfigPanel filter="provider" />
            </SoftFold>
            <SoftFold title="路由 / 内部 LLM / 服务" hint="smart_routing · internal · services">
              <ModelConfigPanel filter="routing" />
              <ModelConfigPanel filter="internal" />
              <ModelConfigPanel filter="services" />
            </SoftFold>
            <SoftFold title="运维" hint="align / transfer / 发现">
              <AgentOpsPanel />
            </SoftFold>
          </div>
          <div className="space-y-3">
            <SoftFold title="智能体实例 / 角色" hint="实例卡 · 加载角色 · 配置">
              <AgentRuntimePanel />
            </SoftFold>
            <SoftFold title="其他运行时" hint="frameworks / codex / claude">
              <SectionEditor title="其他运行时配置" allow={AGENT_RUNTIME_OTHER_SECTIONS} sections={sections} />
            </SoftFold>
          </div>
        </div>
      </div>
    );
  }

  if (v === "bus") {
    return (
      <div className="space-y-4">
        <header>
          <p className="hud-label">Bus</p>
          <h2 className="mt-1 font-display text-2xl tracking-wide">总线</h2>
          <p className="mt-1 text-sm text-mute">路径 · 权限 · A2A · 调度段 · 默认收起</p>
        </header>
        <BusExtrasPanel />
        <SoftFold title="调度 / 工作流 / 自动化 / 端口" hint="可编辑运行段表单">
          <SectionEditor title="总线 sections" allow={BUS_SECTIONS} sections={sections} />
        </SoftFold>
      </div>
    );
  }

  // full / legacy: token + form panels + all sections
  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Configuration</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide text-frost">配置 / Token</h2>
        <p className="mt-1 text-sm text-mute">各区块默认收起 · 点标题展开</p>
      </header>
      <SoftFold title="API / Token">
        <GearPanel />
      </SoftFold>
      <SoftFold title="技能源">
        <SkillsSourcePanel />
      </SoftFold>
      <SoftFold title="资产路径">
        <AssetPathsPanel />
      </SoftFold>
      <SoftFold title="模型 Provider">
        <ModelConfigPanel filter="provider" />
      </SoftFold>
      <SoftFold title="智能体实例 / 角色">
        <AgentRuntimePanel />
      </SoftFold>
      <SoftFold title="模型路由 / 服务 / 全部 sections" hint="兜底编辑">
        <ModelConfigPanel filter="routing" />
        <ModelConfigPanel filter="internal" />
        <ModelConfigPanel filter="services" />
        <SectionEditor title="全部 sections" allow={null} sections={sections} />
      </SoftFold>
    </div>
  );
}
