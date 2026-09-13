import { useEffect, useState } from "react";
import { api, formatSettingsEffects } from "../lib/api";
import { SchemaFields, asRecord, type FieldSpec } from "./SchemaFields";

/**
 * 左栏「模型配置」— smart_routing / mailbus_internal_llm(providers) / services 三张卡片。
 * providers 是 mailbus 层配置（store/config.json → mailbus_internal_llm.providers），
 * 保存走 { patch } deep-merge；services 包装为 { services }。
 */

type SectionResp = Record<string, unknown>;

const LLM_PROTOCOL_OPTIONS: Record<string, string> = {
  openai: "OpenAI 兼容",
  anthropic: "Anthropic 原生",
  ollama: "Ollama 本机",
  stub: "测试桩（Stub）",
};

/** 协议类型的三态说明（编辑态下拉下方展示） */
const LLM_PROTOCOL_HELP: Record<string, string> = {
  openai: "走 OpenAI 兼容 API，适用 DeepSeek / GLM / Qwen / MiniMax 等绝大多数云端模型。",
  anthropic: "走 Anthropic Messages API（原生），适用 Claude 系列；base_url 可留空走默认端点。",
  ollama: "本机 Ollama 服务，无需 API Key。",
  stub: "内部测试占位，不发起真实调用。",
};

const LLM_PROVIDER_FIELDS: FieldSpec[] = [
  {
    kind: "enum",
    key: "protocol",
    label: "协议类型",
    options: LLM_PROTOCOL_OPTIONS,
    help: "OpenAI 兼容：DeepSeek/GLM/Qwen 等；Anthropic 原生：Claude；Ollama：本机服务；Stub：测试桩。",
  },
  {
    kind: "string",
    key: "base_url",
    label: "Base URL",
    placeholder: "https://api.deepseek.com/v1（anthropic 可留空=默认端点）",
  },
  { kind: "string", key: "model", label: "默认模型", placeholder: "deepseek-chat / claude-sonnet-4-5 / qwen-max" },
  { kind: "string", key: "api_key_env", label: "API Key 环境变量", placeholder: "DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / …" },
  { kind: "string", key: "api_key", label: "API Key（留空不更新）", secret: true, placeholder: "***" },
  { kind: "number", key: "context_window", label: "上下文窗口" },
  { kind: "boolean", key: "supports_function_calling", label: "支持 Function Calling" },
  { kind: "boolean", key: "supports_vision", label: "支持视觉" },
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
      setMsg(formatSettingsEffects(r.data, `已保存 ${section}（可能需要重启生效）`));
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
      setMsg(formatSettingsEffects(r.data, `已保存 ${section}（JSON）`));
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

/** 详情只读展示：把 provider 关键字段渲染成 key-value 列表。 */
function ProviderDetail({ value }: { value: Record<string, unknown> }) {
  const protocol = String(value.protocol || "");
  const protocolLabel = LLM_PROTOCOL_OPTIONS[protocol] || protocol || "未设置";
  const caps = [
    value.supports_function_calling === true ? "Function Calling" : null,
    value.supports_vision === true ? "视觉" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const rows: { k: string; v: string }[] = [
    { k: "协议类型", v: protocolLabel },
    { k: "Base URL", v: String(value.base_url || "（留空）") },
    { k: "默认模型", v: String(value.model || "（未填）") },
    { k: "API Key 环境变量", v: String(value.api_key_env || "（未填）") },
    { k: "API Key", v: value.api_key_configured === true ? "已配置（掩码存储）" : "未配置" },
    { k: "上下文窗口", v: value.context_window == null ? "—" : String(value.context_window) },
    { k: "能力", v: caps || "—" },
    { k: "超时(秒)", v: value.timeout_seconds == null ? "—" : String(value.timeout_seconds) },
    { k: "Temperature", v: value.temperature == null ? "—" : String(value.temperature) },
    { k: "Max Tokens", v: value.max_tokens == null ? "—" : String(value.max_tokens) },
  ];
  return (
    <div className="space-y-2">
      {LLM_PROTOCOL_HELP[protocol] && (
        <p className="rounded bg-white/[0.03] px-2 py-1.5 text-[11px] leading-relaxed text-mute">
          {LLM_PROTOCOL_HELP[protocol]}
        </p>
      )}
      <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.k} className="flex items-baseline justify-between gap-2 border-b border-white/[0.04] pb-1">
            <dt className="shrink-0 text-[10px] uppercase tracking-wide text-mute">{r.k}</dt>
            <dd className="truncate text-right font-mono text-[11px] text-frost" title={r.v}>
              {r.v}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** 单个 provider 卡片：默认收起 → 点击展开详情 → 右上角编辑 → 左下角独立保存。 */
function ProviderCard({
  name,
  value,
  busy,
  onSave,
  onDelete,
}: {
  name: string;
  value: Record<string, unknown>;
  busy: boolean;
  onSave: (name: string, fields: Record<string, unknown>) => Promise<boolean>;
  onDelete: (name: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const protocol = String(value.protocol || "");
  const protocolLabel = LLM_PROTOCOL_OPTIONS[protocol] || protocol || "未设置";
  const model = String(value.model || "");

  if (!expanded) {
    return (
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 text-left transition hover:border-frost/30 hover:bg-white/[0.04]"
        onClick={() => setExpanded(true)}
      >
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className="font-mono text-sm text-frost">{name}</span>
          <span className="rounded px-1.5 py-0.5 text-[10px] text-cyan-signal ring-1 ring-cyan/20">
            {protocolLabel}
          </span>
          {model && <span className="truncate font-mono text-[11px] text-mute">{model}</span>}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] ring-1 ${
              value.api_key_configured === true ? "text-mint ring-mint/30" : "text-mute ring-rail/70"
            }`}
          >
            {value.api_key_configured === true ? "已配置 Key" : "未配置 Key"}
          </span>
          <span className="text-[11px] text-frost/40">›</span>
        </span>
      </button>
    );
  }

  return (
    <div className="soft-inset space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <p className="font-mono text-sm text-frost">{name}</p>
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] ring-1 ${
              value.api_key_configured === true ? "text-mint ring-mint/30" : "text-mute ring-rail/70"
            }`}
          >
            {value.api_key_configured === true ? "已配置 Key" : "未配置 Key"}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {editing ? (
            <button
              type="button"
              className="hud-btn !px-2"
              disabled={saving}
              onClick={() => {
                setEditing(false);
                setDraft(value);
              }}
            >
              取消
            </button>
          ) : (
            <>
              <button
                type="button"
                className="hud-btn !px-2"
                disabled={busy}
                onClick={() => {
                  setDraft(value);
                  setEditing(true);
                }}
              >
                编辑
              </button>
              <button
                type="button"
                className="text-xs text-mute hover:text-flare"
                disabled={busy}
                onClick={() => onDelete(name)}
              >
                删除
              </button>
              <button type="button" className="text-xs text-mute hover:text-frost/70" onClick={() => setExpanded(false)}>
                收起
              </button>
            </>
          )}
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          <SchemaFields
            specs={LLM_PROVIDER_FIELDS}
            value={draft}
            onChange={(k, v) => setDraft((m) => ({ ...m, [k]: v }))}
            disabled={saving}
          />
          <div className="flex items-center justify-between border-t border-white/[0.06] pt-2">
            <button
              type="button"
              className="hud-btn-amber"
              disabled={saving}
              onClick={() => {
                void (async () => {
                  setSaving(true);
                  const fields: Record<string, unknown> = { ...draft };
                  delete fields.api_key_configured;
                  const ok = await onSave(name, fields);
                  setSaving(false);
                  if (ok) setEditing(false);
                })();
              }}
            >
              {saving ? "保存中…" : "保存"}
            </button>
            <span className="text-[11px] text-mute">只保存当前卡片</span>
          </div>
        </div>
      ) : (
        <ProviderDetail value={value} />
      )}
    </div>
  );
}

/** Provider 面板：列出 mailbus_internal_llm.providers，卡片收起/展开，逐卡独立保存。 */
export function ProviderPanel() {
  const [providers, setProviders] = useState<Record<string, Record<string, unknown>>>({});
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
        Object.entries(p)
          .filter(([, v]) => v && typeof v === "object")
          .map(([k, v]) => [k, asRecord(v)]),
      ),
    );
  };
  useEffect(() => {
    void load();
  }, []);

  const names = Object.keys(providers);

  async function saveOne(name: string, fields: Record<string, unknown>): Promise<boolean> {
    setBusy(true);
    setMsg("");
    const r = await api("/api/settings/section/mailbus_internal_llm", {
      method: "POST",
      body: JSON.stringify({ patch: { providers: { [name]: fields } } }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(formatSettingsEffects(r.data, `已保存 ${name}（可能需要重启生效）`));
      void load();
      return true;
    }
    setMsg(r.error);
    return false;
  }

  async function removeProvider(name: string) {
    if (!window.confirm(`删除 provider「${name}」？`)) return;
    setBusy(true);
    setMsg("");
    const r = await api("/api/settings/section/mailbus_internal_llm", {
      method: "POST",
      body: JSON.stringify({ patch: { providers: { [name]: null } } }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(`已删除 ${name}`);
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
    setProviders((m) => ({ ...m, [name]: { protocol: "openai", base_url: "", model: "", api_key_env: "" } }));
    setNewName("");
    setAdding(false);
    setMsg("");
  }

  return (
    <div className="soft-inset space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="hud-label">LLM Providers（mailbus 层）</p>
          <p className="text-[11px] text-mute">deepseek / glm / qwen … 点卡片展开详情，右上角「编辑」修改</p>
        </div>
        <div className="flex gap-2">
          {!adding && (
            <button type="button" className="hud-btn !px-2" disabled={busy} onClick={() => setAdding(true)}>
              + 新增 Provider
            </button>
          )}
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
      {names.map((name) => (
        <ProviderCard
          key={name}
          name={name}
          value={providers[name] || {}}
          busy={busy}
          onSave={saveOne}
          onDelete={removeProvider}
        />
      ))}
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
