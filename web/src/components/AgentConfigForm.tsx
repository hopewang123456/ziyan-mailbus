import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { SchemaFields, type FieldSpec } from "./SchemaFields";
import { HudL3Modal } from "./HudL3Modal";

/**
 * 智能体配置表单 — 每个 agent 一张卡片，全部字段表单化。
 * 保存走 /api/settings/section/agents 的 { agent_id, fields } 格式（见 lib/adapters/config/config_admin.py）。
 */

export type AgentFormItem = {
  id: string;
  name?: string;
  role?: string;
  type?: string;
  type_label?: string;
  type_note?: string;
  models?: string[];
  provider?: string;
  max_concurrency?: number;
  launch?: Record<string, unknown>;
  enabled?: boolean;
  native_config_path?: string;
  install_path?: string;
  install_path_default?: string;
  install_configured?: boolean;
  run_target?: string;
  run_targets?: string[];
  host?: string;
  port?: number | string | null;
  instance_id?: string;
  custom_paths?: boolean;
  paths?: Record<string, string>;
  skill_groups?: string[];
  persona_files?: string[];
  has_browser?: boolean;
  has_desktop?: boolean;
  [k: string]: unknown;
};

/** Members / 自定义资产路径 — 卡片内可见可改 */
const PATH_FIELD_KEYS: { key: string; label: string; group?: "avatar" | "members" }[] = [
  { key: "portrait", label: "静帧肖像", group: "avatar" },
  { key: "avatar_animated", label: "动态肖像", group: "avatar" },
  { key: "members_root", label: "Members 根", group: "members" },
  { key: "framework_config", label: "框架 config（公共）", group: "members" },
  { key: "framework_skills", label: "框架 skills（公共，全员加载）", group: "members" },
  { key: "persona", label: "人设目录", group: "members" },
  { key: "config", label: "角色 config（私有）", group: "members" },
  { key: "skills", label: "私有 skills（仅本角色）", group: "members" },
  { key: "memory", label: "memory（私有）", group: "members" },
  { key: "rules", label: "个人 rules（私有，框架优先）", group: "members" },
  { key: "path_map_person", label: "path-map", group: "members" },
];

function avatarPreviewUrl(agentId: string, paths: Record<string, string>): string {
  const p = (paths.portrait || "").trim();
  if (p) return `/api/agent-avatar/${encodeURIComponent(agentId)}/portrait?t=${encodeURIComponent(p.slice(-24))}`;
  return `/avatars/${encodeURIComponent(agentId)}_portrait.png`;
}

function LaunchJsonFallback({
  value,
  onApply,
  disabled,
}: {
  value: unknown;
  onApply: (v: unknown) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  function openEdit() {
    setText(value == null ? "" : JSON.stringify(value, null, 2));
    setErr("");
    setOpen(true);
  }
  function commit() {
    try {
      onApply(text.trim() ? JSON.parse(text) : undefined);
      setErr("");
      setOpen(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "JSON 无效");
    }
  }
  return (
    <div className="space-y-1 border-t border-white/[0.06] pt-2">
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-mute">launch 完整 JSON（表单之外的高级字段）</span>
        <button type="button" className="hud-btn !px-2" disabled={disabled} onClick={() => (open ? setOpen(false) : openEdit())}>
          {open ? "收起" : "编辑"}
        </button>
      </div>
      {open && (
        <div className="space-y-1">
          <textarea
            className="hud-input w-full font-mono text-xs"
            rows={5}
            value={text}
            disabled={disabled}
            spellCheck={false}
            onChange={(e) => setText(e.target.value)}
          />
          <button type="button" className="hud-btn" disabled={disabled} onClick={commit}>
            应用 launch JSON
          </button>
        </div>
      )}
      {err && <p className="text-xs text-flare">{err}</p>}
    </div>
  );
}

export function AgentConfigForm({
  items,
  modelTiers,
  skillGroups,
  inline = false,
}: {
  items: AgentFormItem[];
  modelTiers: string[];
  skillGroups?: string[];
  /** 嵌入子页时直接展开表单，不再套一层弹窗 */
  inline?: boolean;
}) {
  const [values, setValues] = useState<Record<string, Record<string, unknown>>>(() =>
    Object.fromEntries(items.map((it) => [it.id, { ...it }])),
  );
  const [dirty, setDirty] = useState<Record<string, Record<string, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setValues(Object.fromEntries(items.map((it) => [it.id, { ...it }])));
    setDirty({});
  }, [items]);

  function patchValue(id: string, key: string, v: unknown) {
    setValues((m) => ({ ...m, [id]: { ...(m[id] || {}), [key]: v } }));
    setDirty((m) => ({ ...m, [id]: { ...(m[id] || {}), [key]: true } }));
  }

  async function saveAgent(id: string): Promise<boolean> {
    const d = dirty[id] || {};
    const keys = Object.keys(d);
    if (!keys.length) {
      setMsg(`${id}: 无改动`);
      return true;
    }
    setBusy(true);
    setMsg("");
    const fields: Record<string, unknown> = {};
    for (const k of keys) fields[k] = values[id][k];
    const r = await api<{
      status?: string;
      auth_required?: boolean;
      obtain_credential_url?: string;
      auth_hint?: string;
      persona_warning?: string;
      persona_missing?: { path?: string }[];
    }>(`/api/settings/section/agents`, {
      method: "POST",
      body: JSON.stringify({ agent_id: id, fields }),
    });
    setBusy(false);
    if (r.ok) {
      setDirty((m) => {
        const n = { ...m };
        delete n[id];
        return n;
      });
      const data = r.data || {};
      if (data.auth_required && data.obtain_credential_url) {
        setMsg(`${id}: ${data.auth_hint || "需要登录凭证，已打开网页端"}`);
        try {
          window.open(String(data.obtain_credential_url), "_blank", "noopener,noreferrer");
        } catch {
          /* ignore */
        }
      } else if (data.persona_warning) {
        const missing = (data.persona_missing || []).map((m) => m.path).join("、");
        setMsg(`${id}: ${data.persona_warning}${missing ? `（${missing}）` : ""}`);
      } else {
        setMsg(`已保存 ${id}（可能需要重启生效）`);
      }
      return true;
    }
    setMsg(`${id}: ${r.error}`);
    return false;
  }

  return (
    <div className="space-y-3">
      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
      {items.map((it) => {
        const val = values[it.id] || {};
        const isDirty = Object.keys(dirty[it.id] || {}).length > 0;
        return (
          <AgentCard
            key={it.id}
            it={it}
            val={val}
            isDirty={isDirty}
            busy={busy}
            modelTiers={modelTiers}
            skillGroups={skillGroups}
            inline={inline}
            onSave={() => saveAgent(it.id)}
            onChange={(k, v) => patchValue(it.id, k, v)}
          />
        );
      })}
    </div>
  );
}

function specsFor(modelTiers: string[]): FieldSpec[] {
  // 角色卡只收角色级字段；实例级（type/host/port/run_target/install_path/custom_paths）归实例卡。
  return [
    { kind: "string", key: "name", label: "名称" },
    { kind: "string", key: "role", label: "角色" },
    {
      kind: "stringArray",
      key: "models",
      label: "模型",
      options: modelTiers,
      placeholder: "回车添加模型（如 deepseek-flash）",
    },
    { kind: "string", key: "provider", label: "Provider" },
    { kind: "number", key: "max_concurrency", label: "并发上限", min: 0, max: 10 },
    { kind: "boolean", key: "enabled", label: "工作（退役则下架本角色，不删除）" },
    { kind: "string", key: "native_config_path", label: "原生/Members 配置路径", placeholder: "…/02-members/…/022x1-config" },
    {
      kind: "group",
      key: "auth",
      label: "浏览器鉴权 (auth)",
      help: "鉴权属 agent 本体；此处收口 token/账密，方便 Cockpit 打开浏览器/终端。mode=none 会跳过收口并影响非本机门槛（将警告）。敏感值建议 *_ref → secrets",
      children: [
        {
          kind: "enum",
          key: "mode",
          label: "模式",
          options: {
            none: "无 (none) — 警告：跳过凭据收口",
            token: "Token",
            basic: "Basic",
            header: "Header (预留)",
          },
        },
        { kind: "string", key: "token", label: "Token", secret: true, placeholder: "token 或 token_ref" },
        { kind: "string", key: "username", label: "用户名", placeholder: "username 或 username_ref" },
        { kind: "string", key: "password", label: "密码", secret: true, placeholder: "password 或 password_ref" },
      ],
    },
    {
      kind: "group",
      key: "launch",
      label: "启动 (launch)",
      children: [
        { kind: "string", key: "template", label: "launch 模板", placeholder: "claude_host / codex_docker / …" },
        { kind: "boolean", key: "launch_via_api", label: "API 启动" },
        { kind: "boolean", key: "has_browser", label: "有浏览器入口" },
        {
          kind: "group",
          key: "browser",
          label: "浏览器",
          children: [
            { kind: "string", key: "kind", label: "kind" },
            { kind: "string", key: "url", label: "URL", placeholder: "http://127.0.0.1:{port}/" },
            { kind: "string", key: "web_port", label: "web_port" },
            { kind: "string", key: "dashboard_port", label: "dashboard_port（Hermes）" },
            { kind: "string", key: "gateway_port", label: "gateway_port（OpenClaw）" },
            { kind: "string", key: "ttyd_port", label: "ttyd_port（Codex）" },
            { kind: "string", key: "ttyd_url", label: "ttyd_url" },
          ],
        },
      ],
    },
  ];
}

function MembersPathsSection({
  agentId,
  val,
  disabled,
  onChange,
}: {
  agentId: string;
  val: Record<string, unknown>;
  disabled: boolean;
  onChange: (k: string, v: unknown) => void;
}) {
  const paths =
    val.paths && typeof val.paths === "object" && !Array.isArray(val.paths)
      ? ({ ...(val.paths as Record<string, string>) } as Record<string, string>)
      : {};
  const preview = avatarPreviewUrl(agentId, paths);
  const avatarFields = PATH_FIELD_KEYS.filter((f) => f.group === "avatar");
  const memberFields = PATH_FIELD_KEYS.filter((f) => f.group !== "avatar");
  const filled = PATH_FIELD_KEYS.filter((f) => (paths[f.key] || "").trim()).length;

  function setPath(key: string, v: string) {
    onChange("paths", { ...paths, [key]: v });
  }

  function PathGrid({ fields }: { fields: typeof PATH_FIELD_KEYS }) {
    return (
      <div className="grid gap-2 sm:grid-cols-2">
        {fields.map((f) => (
          <label key={f.key} className="block min-w-0">
            <span className="mb-0.5 block text-[10px] text-mute">{f.label}</span>
            <input
              className="hud-input w-full truncate font-mono text-[11px]"
              value={paths[f.key] || ""}
              disabled={disabled}
              spellCheck={false}
              placeholder={`paths.${f.key}`}
              onChange={(e) => setPath(f.key, e.target.value)}
              title={paths[f.key] || f.key}
            />
          </label>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3 border-t border-white/[0.06] pt-3">
      <div className="flex items-start gap-3">
        <div className="h-16 w-16 shrink-0 overflow-hidden rounded-2xl border border-white/10 bg-abyss/50">
          <img
            src={preview}
            alt=""
            className="h-full w-full object-cover"
            onError={(e) => {
              const el = e.currentTarget;
              el.style.opacity = "0.25";
            }}
          />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[12px] text-frost/90">肖像与 Members 路径</p>
          </div>
          <p className="text-[10px] text-mute">
            角色级路径由框架扫描自动生成（已填 {filled}/{PATH_FIELD_KEYS.length}）；如需整体改「是否自定义」或框架公共 skills/rules，去实例卡配置。
          </p>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-[0.12em] text-mute">肖像</p>
        <PathGrid fields={avatarFields} />
      </div>
      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-[0.12em] text-mute">Members · 资产</p>
        <PathGrid fields={memberFields} />
      </div>
    </div>
  );
}

function SkillGroupSection({
  val,
  groups,
  disabled,
  onChange,
}: {
  val: Record<string, unknown>;
  groups?: string[];
  disabled: boolean;
  onChange: (k: string, v: unknown) => void;
}) {
  const selected = Array.isArray(val.skill_groups) ? (val.skill_groups as string[]) : [];
  const available = (groups || []).filter((g) => g);
  function toggle(g: string) {
    const next = selected.includes(g) ? selected.filter((x) => x !== g) : [...selected, g];
    onChange("skill_groups", next);
  }
  return (
    <div className="space-y-2 border-t border-white/[0.06] pt-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[12px] text-frost/90">技能共享组（skillgroup）</p>
        <span className="text-[10px] text-mute">已选 {selected.length}/{available.length}</span>
      </div>
      <p className="text-[10px] text-mute">
        多选要额外挂载的技能组（仅 skills 有共享性）；最终 skills = 私有 + 组 + 框架公共，同名覆盖 私有 &gt; 组 &gt; 框架。
      </p>
      {available.length === 0 ? (
        <p className="text-[10px] text-mute/80">
          暂无可用组 — 在 skillgroup 根下建一级子目录即可成为一组（默认仓库 <span className="font-mono">skills/skillgroup/</span>，本机可指到 Vault）。
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {available.map((g) => (
            <label key={g} className="flex items-center gap-1.5 text-[11px] text-frost/85">
              <input type="checkbox" checked={selected.includes(g)} disabled={disabled} onChange={() => toggle(g)} />
              <span className="font-mono">{g}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function PersonaFilesSection({
  val,
  disabled,
  onChange,
}: {
  val: Record<string, unknown>;
  disabled: boolean;
  onChange: (k: string, v: unknown) => void;
}) {
  const files = Array.isArray(val.persona_files) ? (val.persona_files as string[]) : [];
  const [text, setText] = useState("");
  function add() {
    const v = text.trim();
    if (!v || files.includes(v)) return;
    onChange("persona_files", [...files, v]);
    setText("");
  }
  function remove(f: string) {
    onChange("persona_files", files.filter((x) => x !== f));
  }
  return (
    <div className="space-y-2 border-t border-white/[0.06] pt-3">
      <p className="text-[12px] text-frost/90">人设（用户添加）</p>
      <p className="text-[10px] text-mute">
        人设 = 框架自动扫描（SOUL.md/CLAUDE.md/AGENTS.md）∪ 此处添加；保存时校验文件存在，缺失会提示可能无法沟通。
      </p>
      <div className="flex flex-wrap gap-1.5">
        {files.map((f) => (
          <span key={f} className="inline-flex items-center gap-1 rounded bg-white/[0.04] px-2 py-0.5 font-mono text-[10px] text-frost/85">
            {f}
            <button type="button" className="text-mute hover:text-flare" disabled={disabled} onClick={() => remove(f)}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="hud-input min-w-0 flex-1 font-mono text-[11px]"
          value={text}
          disabled={disabled}
          spellCheck={false}
          placeholder="添加人设文件路径（如 …/SOUL.md）"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="hud-btn" disabled={disabled || !text.trim()} onClick={add}>
          添加
        </button>
      </div>
    </div>
  );
}

function AgentCard({
  it,
  val,
  isDirty,
  busy,
  modelTiers,
  skillGroups,
  inline = false,
  onSave,
  onChange,
}: {
  it: AgentFormItem;
  val: Record<string, unknown>;
  isDirty: boolean;
  busy: boolean;
  modelTiers: string[];
  skillGroups?: string[];
  inline?: boolean;
  onSave: () => Promise<boolean>;
  onChange: (k: string, v: unknown) => void;
}) {
  const [open, setOpen] = useState(inline);
  const [saving, setSaving] = useState(false);
  const pathMap =
    val.paths && typeof val.paths === "object" && !Array.isArray(val.paths)
      ? (val.paths as Record<string, string>)
      : {};
  const pathHint =
    String(val.native_config_path || "").trim() ||
    String(pathMap.framework_config || "").trim() ||
    String(val.install_path || "").trim();
  const thumb = avatarPreviewUrl(it.id, pathMap);

  const formBody = (
    <div className="space-y-3">
      <SchemaFields
        specs={specsFor(modelTiers)}
        value={val}
        onChange={onChange}
        disabled={busy || saving}
      />
      <MembersPathsSection agentId={it.id} val={val} disabled={busy || saving} onChange={onChange} />
      <SkillGroupSection val={val} groups={skillGroups} disabled={busy || saving} onChange={onChange} />
      <PersonaFilesSection val={val} disabled={busy || saving} onChange={onChange} />
      <LaunchJsonFallback value={val.launch} onApply={(v) => onChange("launch", v)} disabled={busy || saving} />
      <div className="sticky bottom-0 z-[1] flex gap-2 border-t border-white/[0.06] bg-[rgba(12,16,24,0.92)] py-3 backdrop-blur-md">
        <button
          type="button"
          className="hud-btn-amber !rounded-full !px-5"
          disabled={busy || saving}
          onClick={async () => {
            setSaving(true);
            const ok = await onSave();
            setSaving(false);
            if (ok && !inline) setOpen(false);
          }}
        >
          {saving ? "保存中…" : isDirty ? "保存改动" : "保存"}
        </button>
        {!inline ? (
          <button type="button" className="hud-btn !rounded-full" onClick={() => setOpen(false)}>
            取消
          </button>
        ) : null}
        {isDirty ? <span className="self-center text-[11px] text-amber-signal">有未保存改动</span> : null}
      </div>
    </div>
  );

  if (inline) {
    return <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-3 sm:p-4">{formBody}</div>;
  }

  return (
    <>
      <button
        type="button"
        className="group flex w-full items-center gap-3 rounded-md border border-rail/50 bg-abyss/25 px-2.5 py-2 text-left transition hover:border-frost/35 hover:bg-abyss/45"
        onClick={() => setOpen(true)}
      >
        <span className="h-10 w-10 shrink-0 overflow-hidden rounded border border-rail/50 bg-hull/40">
          <img
            src={thumb}
            alt=""
            className="h-full w-full object-cover opacity-90 transition group-hover:opacity-100"
            onError={(e) => {
              e.currentTarget.style.opacity = "0.2";
            }}
          />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex min-w-0 items-center gap-2">
            <span className="font-mono text-sm text-frost">{it.id}</span>
            <span className="rounded px-1.5 py-0.5 text-[10px] text-mute ring-1 ring-rail/70">
              {it.type_label || it.type || "?"}
            </span>
            {val.run_target ? (
              <span className="text-[10px] text-cyan-signal">{String(val.run_target)}</span>
            ) : null}
            {val.port != null && val.port !== "" ? (
              <span className="font-mono text-[10px] text-mute">:{String(val.port)}</span>
            ) : null}
          </span>
          {pathHint ? (
            <span className="truncate font-mono text-[10px] text-mute" title={pathHint}>
              {pathHint}
            </span>
          ) : (
            <span className="text-[10px] text-flare/80">未配置路径</span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {val.enabled === true && <span className="text-[10px] text-mint">on</span>}
          {val.enabled === false && <span className="text-[10px] text-flare">off</span>}
          {isDirty && <span className="text-[10px] text-amber">改</span>}
          <span className="text-[11px] text-frost/40">›</span>
        </span>
      </button>
      <HudL3Modal title={`${it.id} · 智能体配置`} open={open} onClose={() => setOpen(false)}>
        {formBody}
      </HudL3Modal>
    </>
  );
}

