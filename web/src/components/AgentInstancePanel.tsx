/**
 * 模型旋钮 · 右侧 Agent 配置（双层 SoT）
 * 1) 实例卡（框架） 2) 加载角色 3) 角色子页配置
 *
 * 实例卡字段：run_target · Agent 类型 · 父路径(+自定义) · 访问地址 · 登录凭证
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { AgentConfigForm, type AgentFormItem } from "./AgentConfigForm";

type AuthBlock = {
  mode?: string;
  token?: string;
  user?: string;
  password?: string;
  token_ref?: string;
  password_ref?: string;
};

type Instance = {
  id?: string;
  type?: string;
  label?: string;
  run_target?: string;
  run_targets?: string[];
  install_path?: string;
  install_path_default?: string;
  host?: string;
  port?: number | string | null;
  role_ids?: string[];
  paths?: Record<string, string>;
  custom_paths?: boolean;
  enabled?: boolean;
  distro?: string;
  gate_passed?: boolean;
  auth?: AuthBlock;
  auth_summary?: { mode?: string; authed?: boolean; configured?: boolean; generated?: boolean };
  auth_required?: boolean;
  native_config_path?: string;
};

type AgentsResp = {
  agents?: AgentFormItem[];
  agent_instances?: Record<string, Instance>;
  model_tiers?: string[];
  agent_types?: Record<string, { label?: string; note?: string }>;
  skillgroup?: { root?: string; groups?: string[] };
};

const RUN_LABELS: Record<string, string> = {
  windows: "Windows",
  wsl: "WSL",
  linux: "Linux",
  docker: "Docker",
};

const DISTRO_LABELS: Record<string, string> = {
  auto: "自动",
  ubuntu: "Ubuntu",
  centos: "CentOS",
};

const INSTANCE_PATH_KEYS: { key: string; label: string }[] = [
  { key: "skills", label: "框架公共 skills（全员）" },
  { key: "rules", label: "框架公共 rules（全员）" },
  { key: "llm", label: "LLM 配置路径" },
  { key: "persona", label: "人设默认目录" },
  { key: "memory", label: "memory 路径" },
  { key: "framework_config", label: "框架 config" },
  { key: "framework_skills", label: "框架 skills 目录" },
];

type View = "instances" | "roles" | "edit-instance" | "edit-role";

function accessUrl(inst: Pick<Instance, "host" | "port">): string {
  const host = (inst.host || "127.0.0.1").trim() || "127.0.0.1";
  const port = inst.port;
  if (port == null || String(port).trim() === "") return `http://${host}/`;
  return `http://${host}:${String(port)}/`;
}

function authBadge(inst: Instance): { text: string; className: string } {
  if (inst.auth_summary?.authed) return { text: "已持有凭证", className: "agent-chip agent-chip-live" };
  if (inst.auth_required) return { text: "需登录凭证", className: "agent-chip agent-chip-warn" };
  return { text: "免登可选", className: "agent-chip" };
}

const TILE_GLOW: Record<string, string> = {
  hermes: "radial-gradient(120% 90% at 100% 0%, rgba(232,160,69,0.22), transparent 55%)",
  hermes_profile: "radial-gradient(120% 90% at 100% 0%, rgba(232,160,69,0.22), transparent 55%)",
  openclaw: "radial-gradient(120% 90% at 100% 0%, rgba(0,212,255,0.2), transparent 55%)",
  codex: "radial-gradient(120% 90% at 100% 0%, rgba(120,170,255,0.2), transparent 55%)",
  claude_code: "radial-gradient(120% 90% at 100% 0%, rgba(255,140,110,0.2), transparent 55%)",
  opencode: "radial-gradient(120% 90% at 100% 0%, rgba(90,210,160,0.18), transparent 55%)",
  cursor: "radial-gradient(120% 90% at 100% 0%, rgba(200,210,230,0.16), transparent 55%)",
};

function friendlyTitle(inst: Instance, typeLabel: string): string {
  const raw = (inst.label || "").trim();
  if (raw && !raw.includes("@") && !raw.startsWith("inst-")) return raw;
  return typeLabel.replace(/\s+(Agent|Profile|Gateway|CLI)$/i, "").trim() || typeLabel;
}

function RoleFaceStack({ roleIds }: { roleIds: string[] }) {
  const show = roleIds.slice(0, 4);
  const extra = roleIds.length - show.length;
  if (roleIds.length === 0) {
    return (
      <div className="agent-face-stack">
        <span className="agent-face-fallback flex items-center justify-center text-[10px] text-mute">+</span>
      </div>
    );
  }
  return (
    <div className="agent-face-stack">
      {show.map((id) => (
        <img
          key={id}
          src={`/api/agent-avatar/${encodeURIComponent(id)}/portrait`}
          alt=""
          title={id}
          onError={(e) => {
            e.currentTarget.style.opacity = "0.35";
          }}
        />
      ))}
      {extra > 0 ? <span className="agent-face-more">+{extra}</span> : null}
    </div>
  );
}

export function AgentRuntimePanel() {
  const [items, setItems] = useState<AgentFormItem[]>([]);
  const [instances, setInstances] = useState<Record<string, Instance>>({});
  const [modelTiers, setModelTiers] = useState<string[]>([]);
  const [agentTypes, setAgentTypes] = useState<Record<string, { label?: string; note?: string }>>({});
  const [skillGroups, setSkillGroups] = useState<string[]>([]);
  const [view, setView] = useState<View>("instances");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [roleEditId, setRoleEditId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [scanMsg, setScanMsg] = useState("");
  const [scanResult, setScanResult] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState<Instance>({
    type: "hermes_profile",
    run_target: "docker",
    host: "127.0.0.1",
    install_path: "",
    custom_paths: false,
    enabled: true,
    distro: "auto",
    paths: {},
    auth: { mode: "none" },
  });

  const load = useCallback(async () => {
    setLoading(true);
    const r = await api<AgentsResp>("/api/settings/section/agents");
    setLoading(false);
    if (!r.ok) {
      setErr(r.error);
      return;
    }
    setItems(r.data.agents || []);
    setInstances(r.data.agent_instances || {});
    setModelTiers(r.data.model_tiers || []);
    setAgentTypes(r.data.agent_types || {});
    setSkillGroups(r.data.skillgroup?.groups || []);
    setErr("");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const instanceList = useMemo(
    () => Object.values(instances || {}).filter((x) => x && x.id),
    [instances],
  );
  const active = activeId ? instances[activeId] : null;
  const roles = useMemo(() => {
    if (!active) return [];
    const ids = active.role_ids || [];
    return items.filter((it) => ids.includes(it.id) || it.instance_id === active.id);
  }, [active, items]);
  const roleEditItem = roleEditId ? items.find((x) => x.id === roleEditId) : null;

  async function loadRoles() {
    if (!activeId) return;
    setBusy(true);
    setMsg("");
    const r = await api<{ count?: number; created?: string[] }>("/api/agent-instances/load-roles", {
      method: "POST",
      body: JSON.stringify({ instance_id: activeId }),
    });
    setBusy(false);
    if (!r.ok) {
      setMsg(r.error);
      return;
    }
    setMsg(`已加载 ${r.data.count ?? 0} 个角色（新建 ${(r.data.created || []).length}）`);
    await load();
  }

  async function saveInstance(fields: Instance, instanceId?: string) {
    setBusy(true);
    setMsg("");
    const r = await api<{
      instance?: Instance;
      auth_required?: boolean;
      obtain_credential_url?: string;
      auth_hint?: string;
    }>("/api/agent-instances", {
      method: "POST",
      body: JSON.stringify({ instance_id: instanceId, fields }),
    });
    setBusy(false);
    if (!r.ok) {
      setMsg(r.error);
      return null;
    }
    const data = r.data || {};
    if (data.auth_required && data.obtain_credential_url) {
      setMsg(data.auth_hint || "需要登录凭证，已打开网页端");
      try {
        window.open(String(data.obtain_credential_url), "_blank", "noopener,noreferrer");
      } catch {
        /* ignore */
      }
    } else {
      setMsg("实例已保存");
    }
    await load();
    return data.instance || null;
  }

  async function scanInstance() {
    // 实例级扫描验证：验证 install_path，写回实例级 install_path/run_target/distro/gate_passed。
    const iid = draft.id;
    if (!iid) {
      setMsg("先「保存实例」再扫描验证");
      return;
    }
    setBusy(true);
    setScanMsg("");
    setScanResult(null);
    const r = await api<Record<string, unknown>>("/api/agents/scan", {
      method: "POST",
      body: JSON.stringify({
        instance_id: iid,
        framework: String(draft.type || ""),
        install_path: String(draft.install_path || "").trim(),
        run_target: String(draft.run_target || "windows"),
        distro: String(draft.distro || "auto"),
      }),
    });
    setBusy(false);
    if (r.ok) {
      setScanResult(r.data || {});
      await load();
    } else {
      setScanMsg(r.error);
    }
  }

  function openRoles(id: string) {
    setActiveId(id);
    setView("roles");
    setMsg("");
    // 点实例卡 → 自动发现并挂上该框架下全部角色（员工）
    void (async () => {
      setBusy(true);
      const r = await api<{ count?: number; created?: string[] }>("/api/agent-instances/load-roles", {
        method: "POST",
        body: JSON.stringify({ instance_id: id }),
      });
      setBusy(false);
      if (!r.ok) {
        setMsg(r.error);
        await load();
        return;
      }
      setMsg(`已加载 ${r.data.count ?? 0} 个角色（新建 ${(r.data.created || []).length}）`);
      await load();
    })();
  }

  function openEditInstance(inst?: Instance) {
    if (inst) {
      setDraft({
        ...inst,
        paths: { ...(inst.paths || {}) },
        auth: { mode: (inst.auth?.mode as string) || (inst.auth_required ? "token" : "none"), ...(inst.auth || {}) },
      });
      setActiveId(inst.id || null);
    } else {
      setDraft({
        type: "hermes_profile",
        run_target: "docker",
        host: "127.0.0.1",
        install_path: "",
        label: "",
        custom_paths: false,
        enabled: true,
        distro: "auto",
        paths: {},
        auth: { mode: "token" },
      });
      setActiveId(null);
    }
    setView("edit-instance");
    setMsg("");
    setScanMsg("");
    setScanResult(null);
  }

  function setPath(key: string, v: string) {
    setDraft((d) => {
      const paths = { ...(d.paths || {}), [key]: v };
      const next: Instance = { ...d, paths };
      if (v.trim() && !d.custom_paths) next.custom_paths = true;
      return next;
    });
  }

  function setAuth(patch: Partial<AuthBlock>) {
    setDraft((d) => ({ ...d, auth: { ...(d.auth || {}), ...patch } }));
  }

  /* —— 实例列表 —— */
  if (view === "instances") {
    return (
      <div className="agent-soft-shell space-y-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="font-display text-[1.35rem] font-semibold tracking-[-0.02em] text-frost">你的 Agent</p>
            <p className="mt-1 max-w-md text-[13px] leading-relaxed text-mute">
              一张实例卡 = 一个框架团队。点进去会自动请来全部员工。
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button type="button" className="hud-btn !rounded-full !px-3" disabled={loading} onClick={() => void load()}>
              刷新
            </button>
            <button type="button" className="hud-btn-amber !rounded-full !px-3" onClick={() => openEditInstance()}>
              新实例
            </button>
          </div>
        </div>
        {loading && <p className="text-sm text-mute">正在整理团队…</p>}
        {err && <p className="text-sm text-flare">{err}</p>}
        {!loading && instanceList.length === 0 && (
          <div className="agent-empty-soft">
            <p className="font-display text-base text-frost">还没有实例</p>
            <p className="mt-1 text-sm text-mute">先加一个 Hermes / OpenClaw / Codex… 再把员工请进来。</p>
            <button type="button" className="hud-btn-amber !mt-4 !rounded-full" onClick={() => openEditInstance()}>
              创建第一张实例卡
            </button>
          </div>
        )}
        <ul className="grid gap-3 sm:grid-cols-2">
          {instanceList.map((inst, idx) => {
            const typeLabel = agentTypes[inst.type || ""]?.label || inst.type || "?";
            const n = (inst.role_ids || []).length;
            const badge = authBadge(inst);
            const title = friendlyTitle(inst, typeLabel);
            return (
              <li
                key={inst.id}
                className="agent-tile-in"
                style={{ animationDelay: `${Math.min(idx, 8) * 45}ms` }}
              >
                <button
                  type="button"
                  className="agent-soft-tile"
                  style={{ ["--tile-glow" as string]: TILE_GLOW[inst.type || ""] || TILE_GLOW.openclaw }}
                  onClick={() => openRoles(String(inst.id))}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-display text-[1.05rem] font-semibold tracking-[-0.02em] text-frost">{title}</p>
                      <p className="mt-0.5 text-[12px] text-mute">{typeLabel}</p>
                    </div>
                    <RoleFaceStack roleIds={inst.role_ids || []} />
                  </div>
                  <div className="mt-auto flex flex-wrap items-center gap-1.5">
                    <span className="agent-chip">{RUN_LABELS[inst.run_target || ""] || inst.run_target}</span>
                    <span className={badge.className}>{badge.text}</span>
                    <span className="agent-chip">{n ? `${n} 位员工` : "待加载员工"}</span>
                  </div>
                  <div className="flex items-end justify-between gap-2 border-t border-white/[0.06] pt-2.5">
                    <p className="min-w-0 truncate text-[11px] text-mute/90" title={inst.install_path}>
                      {inst.install_path || "未设配置路径"}
                    </p>
                    <span className="shrink-0 text-[12px] font-medium text-frost/55">打开</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  /* —— 编辑实例 —— */
  if (view === "edit-instance") {
    const typeKeys = Object.keys(agentTypes).filter((k) => k !== "none");
    const targets =
      draft.run_targets && draft.run_targets.length > 0
        ? draft.run_targets
        : (["windows", "wsl", "linux", "docker"] as const);
    const authMode = (draft.auth?.mode || "none").toLowerCase();
    const needsAuth =
      draft.auth_required ??
      ["hermes", "hermes_profile", "openclaw", "codex", "claude_code"].includes(draft.type || "");

    return (
      <div className="agent-soft-shell space-y-4">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="hud-btn !rounded-full !px-3"
            onClick={() => setView(activeId ? "roles" : "instances")}
          >
            返回
          </button>
          <p className="font-display text-[1.2rem] font-semibold tracking-[-0.02em] text-frost">
            {draft.id ? "编辑实例" : "新实例"}
          </p>
        </div>

        {/* 1. 服务器类型 */}
        <fieldset className="space-y-1.5">
          <legend className="text-[10px] uppercase tracking-[0.12em] text-mute">1 · 配置服务器类型</legend>
          <div className="flex flex-wrap gap-3">
            {targets.map((t) => (
              <label key={t} className="flex items-center gap-1 text-[11px] text-frost/80">
                <input
                  type="radio"
                  checked={draft.run_target === t}
                  onChange={() => setDraft((d) => ({ ...d, run_target: t }))}
                />
                {RUN_LABELS[t] || t}
              </label>
            ))}
          </div>
          <p className="text-[10px] text-mute">
            同一框架可装多端（如 hermes 装在 docker 与 Ubuntu 各一个）→ 各建一个实例、各自加载角色。
          </p>
          {draft.run_target === "wsl" || draft.run_target === "linux" ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-[11px] text-mute">发行版：</span>
              {(["auto", "ubuntu", "centos"] as const).map((d) => (
                <label key={d} className="flex items-center gap-1 text-[11px] text-frost/80">
                  <input
                    type="radio"
                    checked={(draft.distro || "auto") === d}
                    onChange={() => setDraft((dd) => ({ ...dd, distro: d }))}
                  />
                  {DISTRO_LABELS[d]}
                </label>
              ))}
              <span className="text-[10px] text-mute">Ubuntu/CentOS 命令不同（apt/ufw vs dnf|yum/firewalld）</span>
            </div>
          ) : null}
        </fieldset>

        {/* 2. Agent 类型 */}
        <label className="block">
          <span className="text-[10px] uppercase tracking-[0.12em] text-mute">2 · Agent 类型</span>
          <select
            className="hud-input mt-0.5 w-full"
            value={draft.type || ""}
            onChange={(e) => {
              const type = e.target.value;
              setDraft((d) => ({
                ...d,
                type,
                auth: {
                  ...(d.auth || {}),
                  mode:
                    ["hermes", "hermes_profile", "openclaw", "codex"].includes(type)
                      ? "token"
                      : type === "claude_code"
                        ? "basic"
                        : "none",
                },
              }));
            }}
          >
            {typeKeys.map((k) => (
              <option key={k} value={k}>
                {agentTypes[k]?.label || k}
              </option>
            ))}
          </select>
          {agentTypes[draft.type || ""]?.note ? (
            <span className="mt-0.5 block text-[10px] text-mute">{agentTypes[draft.type || ""]?.note}</span>
          ) : null}
        </label>

        <label className="block">
          <span className="text-[10px] text-mute">显示名</span>
          <input
            className="hud-input mt-0.5 w-full text-xs"
            value={draft.label || ""}
            onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))}
            placeholder="如 Hermes 主实例"
          />
        </label>

        {/* 3. 配置路径 + 自定义 */}
        <div className="space-y-2 border-t border-rail/40 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-[0.12em] text-mute">3 · 配置路径（默认父路径）</span>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-[11px] text-mute">
                <input
                  type="checkbox"
                  checked={Boolean(draft.custom_paths)}
                  onChange={(e) => setDraft((d) => ({ ...d, custom_paths: e.target.checked }))}
                />
                自定义
              </label>
              <label
                className="flex items-center gap-1.5 text-[11px] text-frost/80"
                title="关闭后该实例下所有角色下架（不参与派发/监测，但不删除角色）"
              >
                <input
                  type="checkbox"
                  checked={draft.enabled !== false}
                  onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
                />
                监测
              </label>
            </div>
          </div>
          <input
            className="hud-input w-full font-mono text-xs"
            value={draft.install_path || ""}
            onChange={(e) => setDraft((d) => ({ ...d, install_path: e.target.value }))}
            placeholder={draft.install_path_default || "如 E:\\hermes-data\\.hermes"}
          />
          <p className="text-[10px] text-mute">
            实例层配置 = 该框架下全员公共（skills/rules 等）；未勾自定义时按父路径约定目录扫描。
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="hud-btn"
              disabled={busy || !draft.install_path?.trim() || !(draft.role_ids && draft.role_ids[0])}
              onClick={() => void scanInstance()}
            >
              {busy ? "扫描中…" : "扫描验证"}
            </button>
            <span className="text-[10px] text-mute">
              {draft.role_ids && draft.role_ids[0]
                ? "验证 install_path 并写回实例级（gate/distro），不覆盖角色启停"
                : "先保存实例并加载角色后可扫描"}
            </span>
          </div>
          {scanMsg && <p className="text-[11px] text-amber-signal">{scanMsg}</p>}
          {scanResult &&
            (() => {
              const gate = (scanResult.gate || {}) as { passed?: boolean; reason?: string; install_root?: string };
              const found = Array.isArray(scanResult.found) ? (scanResult.found as { kind?: string }[]) : [];
              return (
                <>
                  {gate.passed === true ? (
                    <p className="text-[11px] text-mint">路径门禁通过（{gate.install_root}）→ 实例可监测</p>
                  ) : gate.passed === false ? (
                    <p className="text-[11px] text-flare">未通过路径门禁：{gate.reason || "安装路径不存在"}</p>
                  ) : null}
                  {found.length > 0 ? (
                    <p className="text-[10px] text-mute">
                      已发现 {found.length} 项资产（
                      {found
                        .slice(0, 4)
                        .map((a) => a.kind)
                        .join("、")}
                      {found.length > 4 ? "…" : ""}）
                    </p>
                  ) : null}
                </>
              );
            })()}
          {draft.custom_paths ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {INSTANCE_PATH_KEYS.map((f) => (
                <label key={f.key} className="block min-w-0">
                  <span className="mb-0.5 block text-[10px] text-mute">{f.label}</span>
                  <input
                    className="hud-input w-full truncate font-mono text-[11px]"
                    value={(draft.paths || {})[f.key] || ""}
                    spellCheck={false}
                    placeholder={`paths.${f.key}`}
                    onChange={(e) => setPath(f.key, e.target.value)}
                  />
                </label>
              ))}
            </div>
          ) : null}
        </div>

        {/* 4. 访问地址 */}
        <div className="space-y-2 border-t border-rail/40 pt-3">
          <span className="text-[10px] uppercase tracking-[0.12em] text-mute">4 · 访问地址</span>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] text-mute">host</span>
              <input
                className="hud-input mt-0.5 w-full font-mono text-xs"
                value={draft.host || ""}
                onChange={(e) => setDraft((d) => ({ ...d, host: e.target.value }))}
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-mute">port（实例默认）</span>
              <input
                className="hud-input mt-0.5 w-full font-mono text-xs"
                value={draft.port ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, port: e.target.value }))}
              />
            </label>
          </div>
          <p className="font-mono text-[11px] text-cyan-signal">{accessUrl(draft)}</p>
        </div>

        {/* 5. 登录凭证 */}
        <div className="space-y-2 border-t border-rail/40 pt-3">
          <span className="text-[10px] uppercase tracking-[0.12em] text-mute">5 · 登录凭证（非必填）</span>
          <p className="text-[10px] text-mute">
            {needsAuth
              ? "该类型通常需要凭证：首次保存若未填，将自动打开网页端获取；填了则写入 secrets 持有。"
              : "当前类型默认可不填；有浏览器鉴权时可选手动填写。"}
          </p>
          <div className="flex flex-wrap gap-3">
            {(["none", "token", "basic"] as const).map((m) => (
              <label key={m} className="flex items-center gap-1 text-[11px] text-frost/80">
                <input type="radio" checked={authMode === m} onChange={() => setAuth({ mode: m })} />
                {m === "none" ? "无" : m === "token" ? "Token" : "Basic"}
              </label>
            ))}
          </div>
          {authMode === "token" ? (
            <label className="block">
              <span className="text-[10px] text-mute">Token（保存后写入 secrets，卡片只留引用）</span>
              <input
                className="hud-input mt-0.5 w-full font-mono text-xs"
                type="password"
                autoComplete="off"
                value={draft.auth?.token || ""}
                placeholder={draft.auth?.token_ref ? `已持有 ref=${draft.auth.token_ref}` : "粘贴 gateway / session token"}
                onChange={(e) => setAuth({ token: e.target.value })}
              />
            </label>
          ) : null}
          {authMode === "basic" ? (
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="text-[10px] text-mute">用户名</span>
                <input
                  className="hud-input mt-0.5 w-full font-mono text-xs"
                  value={draft.auth?.user || ""}
                  onChange={(e) => setAuth({ user: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-mute">密码</span>
                <input
                  className="hud-input mt-0.5 w-full font-mono text-xs"
                  type="password"
                  autoComplete="off"
                  value={draft.auth?.password || ""}
                  placeholder={draft.auth?.password_ref ? "已持有（留空不改）" : ""}
                  onChange={(e) => setAuth({ password: e.target.value })}
                />
              </label>
            </div>
          ) : null}
        </div>

        {msg && <p className="text-xs text-amber-signal">{msg}</p>}
        <button
          type="button"
          className="hud-btn-amber !rounded-full !px-5"
          disabled={busy || !draft.type}
          onClick={async () => {
            const payload: Instance = {
              type: draft.type,
              run_target: draft.run_target,
              install_path: draft.install_path,
              host: draft.host,
              port: draft.port,
              label: draft.label,
              custom_paths: draft.custom_paths,
              paths: draft.paths,
              auth: draft.auth,
            };
            const saved = await saveInstance(payload, draft.id);
            if (saved?.id) {
              setActiveId(saved.id);
              setDraft((d) => ({ ...d, ...saved, auth: { ...(d.auth || {}), ...(saved.auth || {}), token: "", password: "" } }));
              setView("roles");
            }
          }}
        >
          {busy ? "保存中…" : "保存实例"}
        </button>
      </div>
    );
  }

  /* —— 角色编辑子页（全宽，不再用小弹窗） —— */
  if (view === "edit-role" && roleEditItem) {
    return (
      <div className="agent-soft-shell flex max-h-[min(78vh,820px)] flex-col gap-3 overflow-hidden">
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              className="hud-btn !rounded-full !px-3"
              onClick={() => {
                setRoleEditId(null);
                setView("roles");
                void load();
              }}
            >
              返回团队
            </button>
            <img
              src={`/api/agent-avatar/${encodeURIComponent(roleEditItem.id)}/portrait`}
              alt=""
              className="h-11 w-11 rounded-full object-cover ring-2 ring-white/10"
              onError={(e) => {
                e.currentTarget.style.opacity = "0.35";
              }}
            />
            <div className="min-w-0">
              <p className="truncate font-display text-[1.15rem] font-semibold tracking-[-0.02em] text-frost">
                {roleEditItem.name || roleEditItem.role || roleEditItem.id}
              </p>
              <p className="truncate font-mono text-[11px] text-mute">{roleEditItem.id} · 角色配置</p>
            </div>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
          <AgentConfigForm
            items={[roleEditItem]}
            modelTiers={modelTiers}
            skillGroups={skillGroups}
            inline
          />
        </div>
      </div>
    );
  }

  /* —— 角色子页 —— */
  const activeTitle = friendlyTitle(
    active || {},
    agentTypes[active?.type || ""]?.label || active?.type || "团队",
  );

  return (
    <div className="agent-soft-shell space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="hud-btn !rounded-full !px-3" onClick={() => setView("instances")}>
              全部实例
            </button>
            <button
              type="button"
              className="hud-btn !rounded-full !px-3"
              onClick={() => active && openEditInstance(active)}
            >
              编辑
            </button>
            <button
              type="button"
              className="hud-btn-amber !rounded-full !px-3"
              disabled={busy || !activeId}
              onClick={() => void loadRoles()}
            >
              {busy ? "请来中…" : "重新加载"}
            </button>
          </div>
          <p className="mt-3 font-display text-[1.35rem] font-semibold tracking-[-0.02em] text-frost">{activeTitle}</p>
          <p className="mt-1 text-[13px] text-mute">
            {agentTypes[active?.type || ""]?.label || active?.type} ·{" "}
            {RUN_LABELS[active?.run_target || ""] || active?.run_target} · {authBadge(active || {}).text}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-mute/80" title={active?.install_path}>
            {active?.install_path || "未设父路径"}
          </p>
        </div>
        <RoleFaceStack roleIds={active?.role_ids || roles.map((r) => r.id)} />
      </div>
      {msg && <p className="text-[13px] text-amber-signal">{msg}</p>}
      {busy && roles.length === 0 ? (
        <div className="agent-empty-soft">
          <p className="font-display text-base text-frost">正在请来员工…</p>
          <p className="mt-1 text-sm text-mute">从 Members / 安装目录发现角色中</p>
        </div>
      ) : roles.length === 0 ? (
        <div className="agent-empty-soft">
          <p className="font-display text-base text-frost">还没有员工</p>
          <p className="mt-1 text-sm text-mute">点「重新加载」，或先检查实例的配置路径。</p>
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {roles.map((role, idx) => (
            <li
              key={role.id}
              className="agent-tile-in"
              style={{ animationDelay: `${Math.min(idx, 10) * 40}ms` }}
            >
              <button
                type="button"
                className="agent-role-tile"
                onClick={() => {
                  setRoleEditId(role.id);
                  setView("edit-role");
                }}
              >
                <img
                  src={`/api/agent-avatar/${encodeURIComponent(role.id)}/portrait`}
                  alt=""
                  className="agent-role-portrait"
                  onError={(e) => {
                    e.currentTarget.style.opacity = "0.35";
                  }}
                />
                <div className="min-w-0">
                  <p className="truncate font-display text-[0.95rem] font-semibold tracking-[-0.02em] text-frost">
                    {role.name || role.role || role.id}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[10px] text-mute">{role.id}</p>
                </div>
                <span className="agent-chip">配置</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
