import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { SchemaFields, asRecord, type FieldSpec } from "./SchemaFields";

/**
 * 左栏「模型配置」— smart_routing / mailbus_internal_llm(providers) / services 三张卡片。
 * providers 是 mailbus 层配置（store/config.json → mailbus_internal_llm.providers），
 * 保存走 { patch } deep-merge；services 包装为 { services }。
 */

type SectionResp = Record<string, unknown>;

const LLM_PROVIDER_FIELDS: FieldSpec[] = [
  { kind: "enum", key: "kind", label: "类型", options: ["ollama", "openai_compatible"] },
  { kind: "string", key: "base_url", label: "Base URL", placeholder: "https://api.deepseek.com / …" },
  { kind: "string", key: "model", label: "默认模型", placeholder: "deepseek-chat / glm-4 / qwen-max" },
  { kind: "string", key: "api_key_env", label: "API Key 环境变量", placeholder: "DEEPSEEK_API_KEY / ZHIPU_API_KEY / …" },
  { kind: "string", key: "api_key", label: "API Key（留空不更新）", secret: true, placeholder: "***" },
  { kind: "number", key: "timeout_seconds", label: "超时(秒)" },
  { kind: "number", key: "temperature", label: "Temperature" },
  { kind: "number", key: "max_tokens", label: "Max Tokens" },
];

function SectionFormCard({
  section,
  title,
  help,
  pickValue,
  specsFor,
  buildBody,
  hidden = false,
}: {
  section: string;
  title: string;
  help?: string;
  pickValue: (resp: SectionResp) => Record<string, unknown>;
  specsFor: (resp: SectionResp) => FieldSpec[];
  buildBody?: (value: Record<string, unknown>) => unknown;
  hidden?: boolean;
}) {
  const [value, setValue] = useState<Record<string, unknown>>({});
  const [rawResp, setRawResp] = useState<SectionResp | null>(null);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const r = await api<SectionResp>(`/api/settings/section/${section}`);
    if (!r.ok) {
      setMsg(r.error);
      return;
    }
    setRawResp(r.data);
    setValue(pickValue(r.data));
    setJsonText(JSON.stringify(r.data.data ?? r.data, null, 2));
    setMsg("");
  };
  useEffect(() => {
    if (!hidden) void load();
  }, [section, hidden]);

  async function save() {
    setBusy(true);
    setMsg("");
    const body = buildBody ? buildBody(value) : { patch: value };
    const r = await api(`/api/settings/section/${section}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已保存 ${section}（可能需要重启生效）`);
      void load();
    } else {
      setMsg(r.error);
    }
  }

  async function saveJson() {
    setBusy(true);
    setMsg("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setBusy(false);
      setMsg("JSON 解析失败");
      return;
    }
    const body =
      typeof parsed === "object" && parsed && "patch" in (parsed as object)
        ? parsed
        : { patch: parsed };
    const r = await api(`/api/settings/section/${section}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已保存 ${section}（JSON）`);
      void load();
    } else {
      setMsg(r.error);
    }
  }

  if (hidden) return null;

  return (
    <div className="soft-inset space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="hud-label">{title}</p>
          <p className="font-mono text-[11px] text-mute">{section}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void save()}>
            保存
          </button>
          <button type="button" className="hud-btn !px-2" onClick={() => setJsonOpen((v) => !v)}>
            {jsonOpen ? "收起 JSON" : "原始 JSON"}
          </button>
        </div>
      </div>
      {help && <p className="text-[11px] text-mute">{help}</p>}
      {rawResp && (
        <SchemaFields
          specs={specsFor(rawResp)}
          value={value}
          onChange={(k, v) => setValue((m) => ({ ...m, [k]: v }))}
          disabled={busy}
        />
      )}
      {jsonOpen && (
        <div className="space-y-1 border-t border-rail/50 pt-2">
          <textarea
            className="hud-input w-full font-mono text-xs"
            rows={8}
            value={jsonText}
            disabled={busy}
            spellCheck={false}
            onChange={(e) => setJsonText(e.target.value)}
          />
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void saveJson()}>
            保存 JSON
          </button>
        </div>
      )}
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
    </div>
  );
}

function SmartRoutingCard() {
  return (
    <SectionFormCard
      section="smart_routing"
      title="智能路由 · L0–L3"
      help="推送阶段按复杂度选模型；deepseek-pro 仍须环境变量 MAILBUS_ALLOW_PRO=1。"
      pickValue={(resp) => asRecord(resp.data)}
      specsFor={(resp) => {
        const aliases = Array.isArray(resp.model_aliases) ? (resp.model_aliases as string[]) : [];
        return [
          { kind: "boolean", key: "enabled", label: "启用智能路由" },
          { kind: "boolean", key: "use_ollama", label: "优先本机 Ollama" },
          { kind: "boolean", key: "log_decisions", label: "记录路由决策" },
          {
            kind: "group",
            key: "tier_map",
            label: "Tier 映射（L0–L3 → 模型别名）",
            children: [
              { kind: "enum", key: "L0", label: "L0", options: aliases },
              { kind: "enum", key: "L1", label: "L1", options: aliases },
              { kind: "enum", key: "L2", label: "L2", options: aliases },
              { kind: "enum", key: "L3", label: "L3", options: aliases },
            ],
          },
        ];
      }}
    />
  );
}

function InternalLlmCard() {
  return (
    <SectionFormCard
      section="mailbus_internal_llm"
      title="Internal LLM / Planner · Provider"
      help="providers 为 mailbus 层命名 LLM 连接（deepseek / glm / qwen …）。api_key 仅显示掩码，留空表示不更新；也可只填 api_key_env 走 .env。"
      pickValue={(resp) => asRecord(resp.data)}
      specsFor={(resp) => {
        const data = asRecord(resp.data);
        const providers = asRecord(data.providers);
        const providerGroups: FieldSpec[] = Object.entries(providers).map(([name]) => ({
          kind: "group",
          key: name,
          label: name,
          children: LLM_PROVIDER_FIELDS,
        }));
        const ollama = asRecord(data.ollama);
        const hasOllama = Object.keys(ollama).length > 0;
        const specs: FieldSpec[] = [];
        if (providerGroups.length) {
          specs.push({
            kind: "group",
            key: "providers",
            label: `Providers (${providerGroups.length})`,
            children: providerGroups,
          });
        }
        if (hasOllama) {
          specs.push({
            kind: "group",
            key: "ollama",
            label: "Ollama（本机）",
            children: [
              { kind: "string", key: "base_url", label: "Base URL" },
              { kind: "string", key: "model", label: "模型" },
              { kind: "string", key: "default_model", label: "默认模型" },
              { kind: "number", key: "timeout_seconds", label: "超时(秒)" },
              { kind: "number", key: "temperature", label: "Temperature" },
              { kind: "number", key: "max_tokens", label: "Max Tokens" },
            ],
          });
        }
        specs.push({ kind: "json", key: "routing", label: "routing（JSON）" });
        return specs;
      }}
    />
  );
}

function ServicesCard() {
  return (
    <SectionFormCard
      section="services"
      title="外部服务 · Ollama / AgentMemory"
      help="profiles 分 windows / wsl / docker 三套 URL；改 docker 后需 compose sync。"
      pickValue={(resp) => asRecord(resp.data)}
      specsFor={() => [
        {
          kind: "group",
          key: "ollama",
          label: "Ollama",
          children: [
            { kind: "string", key: "base_url", label: "Base URL" },
            { kind: "string", key: "model", label: "模型" },
            { kind: "json", key: "profiles", label: "profiles（windows/wsl/docker）" },
          ],
        },
        {
          kind: "group",
          key: "agentmemory",
          label: "AgentMemory",
          children: [
            { kind: "string", key: "base_url", label: "Base URL" },
            { kind: "string", key: "health_path", label: "健康检查路径" },
            { kind: "json", key: "profiles", label: "profiles" },
          ],
        },
      ]}
      buildBody={(v) => ({ patch: { services: v } })}
    />
  );
}

type LlmResp = SectionResp & { data?: Record<string, unknown> };

/** Provider 卡片：列出 mailbus_internal_llm.providers，支持筛选 + 新增/删除。 */
export function ProviderPanel() {
  const [providers, setProviders] = useState<Record<string, Record<string, unknown>>>({});
  const [dirty, setDirty] = useState<Record<string, Record<string, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");

  const load = async () => {
    const r = await api<LlmResp>("/api/settings/section/mailbus_internal_llm");
    if (!r.ok) {
      setMsg(r.error);
      return;
    }
    const p = asRecord(asRecord(r.data.data).providers);
    setProviders(
      Object.fromEntries(
        Object.entries(p).map(([k, v]) => [k, asRecord(v)]),
      ),
    );
    setDirty({});
  };
  useEffect(() => {
    void load();
  }, []);

  const names = Object.keys(providers);

  function patchValue(name: string, k: string, v: unknown) {
    setProviders((m) => ({ ...m, [name]: { ...(m[name] || {}), [k]: v } }));
    setDirty((m) => ({ ...m, [name]: { ...(m[name] || {}), [k]: true } }));
  }

  async function save() {
    setBusy(true);
    setMsg("");
    const fields: Record<string, Record<string, unknown>> = {};
    for (const n of names) {
      const d = dirty[n] || {};
      if (Object.keys(d).length) fields[n] = providers[n];
    }
    const r = await api("/api/settings/section/mailbus_internal_llm", {
      method: "POST",
      body: JSON.stringify({ patch: { providers: fields } }),
    });
    setBusy(false);
    if (r.ok) {
      setDirty({});
      setMsg("已保存 providers（可能需要重启生效）");
      void load();
    } else setMsg(r.error);
  }

  function addProvider() {
    const name = newName.trim();
    if (!name) return;
    if (providers[name]) {
      setMsg(`provider ${name} 已存在`);
      return;
    }
    setProviders((m) => ({
      ...m,
      [name]: { kind: "openai_compatible", base_url: "", model: "", api_key_env: "" },
    }));
    setDirty((m) => ({ ...m, [name]: { kind: true, base_url: true, model: true } }));
    setNewName("");
    setAdding(false);
    setMsg("");
  }

  function removeProvider(name: string) {
    const next = { ...providers };
    delete next[name];
    setProviders(next);
    setDirty((m) => ({ ...m, [name]: { ...(m[name] || {}), _remove: true } }));
  }

  return (
    <div className="soft-inset space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="hud-label">LLM Providers（mailbus 层）</p>
          <p className="text-[11px] text-mute">deepseek / glm / qwen … 在此配置 API Key / URL</p>
        </div>
        <div className="flex gap-2">
          {!adding && (
            <button type="button" className="hud-btn !px-2" disabled={busy} onClick={() => setAdding(true)}>
              + 新增 Provider
            </button>
          )}
          <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void save()}>
            保存改动
          </button>
        </div>
      </div>
      {adding && (
        <div className="flex gap-1">
          <input
            className="hud-input flex-1 font-mono text-xs"
            value={newName}
            placeholder="provider 名（如 deepseek / glm / qwen）"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addProvider()}
          />
          <button type="button" className="hud-btn !px-2" onClick={addProvider}>
            添加
          </button>
          <button type="button" className="hud-btn-amber" onClick={() => setAdding(false)}>
            取消
          </button>
        </div>
      )}
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
      {names.length === 0 && !adding && (
        <p className="text-sm text-mute">暂无 provider。点「+ 新增 Provider」添加 deepseek / glm 等。</p>
      )}
      {names.map((name) => {
        const val = providers[name] || {};
        const isDirty = Object.keys(dirty[name] || {}).length > 0;
        return (
          <div key={name} className="soft-inset space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-mono text-sm text-frost">{name}</p>
              <button
                type="button"
                className="text-xs text-mute hover:text-flare"
                disabled={busy}
                onClick={() => removeProvider(name)}
              >
                删除
              </button>
            </div>
            <SchemaFields
              specs={LLM_PROVIDER_FIELDS}
              value={val}
              onChange={(k, v) => patchValue(name, k, v)}
              disabled={busy}
            />
            {isDirty && <p className="text-[11px] text-amber">有未保存改动</p>}
          </div>
        );
      })}
    </div>
  );
}

export type ModelPanelKind = "provider" | "routing" | "internal" | "services";

/** 左栏「模型配置」— 卡片式面板，带 Provider / 路由 / 服务 切换。 */
export function ModelConfigPanel({ filter }: { filter?: ModelPanelKind }) {
  return (
    <div className="soft-panel space-y-3">
      <div>
        <p className="soft-panel-title">模型配置</p>
        <p className="soft-panel-sub">mailbus 层 · Provider / 路由 / 服务</p>
      </div>
      {(!filter || filter === "provider") && <ProviderPanel />}
      {(!filter || filter === "routing") && <SmartRoutingCard />}
      {(!filter || filter === "internal") && <InternalLlmCard />}
      {(!filter || filter === "services") && <ServicesCard />}
    </div>
  );
}
