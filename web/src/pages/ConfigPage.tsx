import { useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "../lib/api";
import { DiscoverPage } from "./DiscoverPage";
import { ErrorAlert } from "../components/ErrorAlert";
import { ModelConfigPanel } from "../components/ModelConfigPanel";
import { AgentRuntimePanel } from "../components/AgentInstancePanel";
import { AssetPathsPanel } from "../components/AssetPathsPanel";
import { BusExtrasPanel } from "../components/BusExtrasPanel";
import { SoftFold } from "../components/SoftFold";
import { ComposeFilesPanel } from "../components/ComposeFilesPanel";
import { AuthSecurityPanel } from "../components/AuthSecurityPanel";
import { RuntimeFrameworkPanel } from "../components/RuntimeFrameworkPanel";
import { BusOpsPanel } from "../components/BusOpsPanel";
import { BusRoutesPanel } from "../components/BusRoutesPanel";
import { WorkflowBoardPage } from "./thin/WorkflowBoardPage";

type TokenInfo = {
  configured?: boolean;
  token_masked?: string;
  hint?: string;
};

function genDeviceToken(): string {
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** 设备 id：zm + 8 位随机 hex，例 zm3a7f9c2e */
function genDeviceId(): string {
  const arr = new Uint8Array(4);
  crypto.getRandomValues(arr);
  return "zm" + Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** 标签旁 ? 悬浮说明 */
function FieldHint({ tip }: { tip: string }) {
  return (
    <span className="field-hint">
      <button type="button" className="field-hint-mark" aria-label={tip} tabIndex={0}>
        ?
      </button>
      <span className="field-hint-tip" role="tooltip">
        {tip}
      </span>
    </span>
  );
}

function FieldLabel({
  children,
  tip,
  required = false,
}: {
  children: ReactNode;
  tip: string;
  required?: boolean;
}) {
  return (
    <span className="hud-label inline-flex items-center">
      {children}
      {required ? <span className="field-required" aria-hidden>*</span> : null}
      <FieldHint tip={tip} />
    </span>
  );
}

function DeviceBridgePanel() {
  type Device = {
    id: string;
    label: string;
    token_env: string;
    token?: string;
    token_configured?: boolean;
    tailscale_ips: string[];
    agent_id: string;
    enabled: boolean;
  };
  type BridgeData = {
    enabled: boolean;
    default_wait_ms: number;
    write_memory: boolean;
    devices: Device[];
  };
  type EditorState =
    | { mode: "list" }
    | { mode: "edit"; index: number; draft: Device }
    | { mode: "create"; draft: Device };

  const [data, setData] = useState<BridgeData | null>(null);
  const [agents, setAgents] = useState<string[]>([]);
  const [editor, setEditor] = useState<EditorState>({ mode: "list" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  function blankDevice(): Device {
    return {
      id: genDeviceId(),
      label: "",
      token_env: "",
      token: "",
      tailscale_ips: [],
      agent_id: agents[0] || "",
      enabled: true,
    };
  }

  async function load() {
    setMsg("");
    const r = await api<{
      data: BridgeData;
      agents: string[];
    }>("/api/settings/section/mailbus_device_bridge");
    if (r.ok) {
      setData(r.data.data);
      setAgents(r.data.agents || []);
    } else setMsg(r.error);
  }

  useEffect(() => {
    void load();
  }, []);

  async function saveGlobal() {
    if (!data) return;
    setBusy(true);
    setMsg("");
    const r = await api(`/api/settings/section/mailbus_device_bridge`, {
      method: "POST",
      body: JSON.stringify({
        patch: {
          enabled: data.enabled,
          write_memory: data.write_memory,
          default_wait_ms: data.default_wait_ms,
        },
      }),
    });
    setBusy(false);
    setMsg(r.ok ? "全局设置已保存" : r.error);
    if (r.ok) void load();
  }

  async function saveDevice(draft: Device, index: number | null) {
    if (!data) return;
    if (!(draft.id || "").trim()) {
      setMsg("请填写设备 id");
      return;
    }
    if (!(draft.agent_id || "").trim()) {
      setMsg("请选择绑定 Agent");
      return;
    }
    const hasToken = Boolean((draft.token || "").trim()) || Boolean((draft.token_env || "").trim()) || Boolean(draft.token_configured);
    if (!hasToken) {
      setMsg("请配置 token（生成内联密钥，或填写 token_env）");
      return;
    }

    const payload: Device = { ...draft };
    // 已配置且未改密钥时，不传空 token，避免后端误清空（后端也会兜底保留）
    if (!(payload.token || "").trim()) {
      delete payload.token;
    }
    delete payload.token_configured;

    const nextDevices =
      index == null
        ? [...data.devices, payload]
        : data.devices.map((d, i) => (i === index ? payload : d));

    setBusy(true);
    setMsg("");
    const r = await api(`/api/settings/section/mailbus_device_bridge`, {
      method: "POST",
      body: JSON.stringify({ patch: { devices: nextDevices } }),
    });
    setBusy(false);
    if (r.ok) {
      setMsg(index == null ? "设备已添加" : "设备已保存");
      setEditor({ mode: "list" });
      void load();
    } else setMsg(r.error);
  }

  async function deleteDevice(index: number) {
    if (!data) return;
    const d = data.devices[index];
    if (!d) return;
    if (!window.confirm(`确定删除设备 ${d.label || d.id}？`)) return;
    const nextDevices = data.devices.filter((_, i) => i !== index);
    setBusy(true);
    setMsg("");
    const r = await api(`/api/settings/section/mailbus_device_bridge`, {
      method: "POST",
      body: JSON.stringify({ patch: { devices: nextDevices } }),
    });
    setBusy(false);
    setMsg(r.ok ? "设备已删除" : r.error);
    if (r.ok) {
      setEditor({ mode: "list" });
      void load();
    }
  }

  if (!data) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-mute">加载中…</p>
        {msg && <p className="text-xs text-amber-signal">{msg}</p>}
      </div>
    );
  }

  // ── 单设备编辑页 ──
  if (editor.mode === "edit" || editor.mode === "create") {
    const draft = editor.draft;
    const isCreate = editor.mode === "create";
    const editIndex = editor.mode === "edit" ? editor.index : null;
    const setDraft = (patch: Partial<Device>) =>
      setEditor((prev) =>
        prev.mode === "list" ? prev : { ...prev, draft: { ...prev.draft, ...patch } },
      );

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm text-frost">{isCreate ? "新增设备" : "编辑设备"}</p>
            <p className="text-xs text-mute">本页只保存这一台设备的绑定，不影响其它设备与全局开关。</p>
          </div>
          <button type="button" className="hud-btn" disabled={busy} onClick={() => setEditor({ mode: "list" })}>
            ← 返回列表
          </button>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="block">
            <FieldLabel
              required
              tip="设备唯一 ID，添加时自动生成（zm + 随机串），也可改成自己的代号。写入消息 from=device:&lt;id&gt;，不要和别的设备重复。"
            >
              id
            </FieldLabel>
            <div className="mt-1 flex gap-1">
              <input
                className="hud-input w-full font-mono text-xs"
                value={draft.id}
                placeholder="zm3a7f9c2e"
                onChange={(e) => setDraft({ id: e.target.value })}
              />
              <button type="button" className="hud-btn shrink-0" onClick={() => setDraft({ id: genDeviceId() })}>
                重新生成
              </button>
            </div>
          </label>
          <label className="block">
            <FieldLabel tip="给人看的备注名，可中文。例：希望的 iPhone。不影响鉴权与路由。">label</FieldLabel>
            <input
              className="hud-input mt-1 w-full font-mono text-xs"
              value={draft.label}
              placeholder="希望的 iPhone"
              onChange={(e) => setDraft({ label: e.target.value })}
            />
          </label>
        </div>

        <div className="space-y-1.5">
          <FieldLabel
            required
            tip="这台手机只能和哪一个 Agent 聊天。点选一个即可；一设备绑一 Agent，多设备可绑不同 Agent。"
          >
            agent_id
          </FieldLabel>
          {agents.length === 0 ? (
            <p className="text-xs text-mute">暂无已注册 Agent</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {agents.map((a) => {
                const active = draft.agent_id === a;
                return (
                  <button
                    key={a}
                    type="button"
                    className={`rounded-lg border px-2.5 py-1 font-mono text-xs transition ${
                      active
                        ? "border-cyan-signal/60 bg-cyan-signal/15 text-frost"
                        : "border-white/10 bg-white/[0.03] text-mute hover:border-white/20 hover:text-frost"
                    }`}
                    onClick={() => setDraft({ agent_id: a })}
                  >
                    {a}
                  </button>
                );
              })}
            </div>
          )}
          {!draft.agent_id && <p className="text-xs text-amber-signal">请选择绑定 Agent</p>}
        </div>

        <div className="space-y-2">
          <FieldLabel
            required
            tip="手机请求时要带的密钥。先用「方式一」点生成即可测通；方式二更安全，适合长期部署。"
          >
            token 配置
          </FieldLabel>
          <p className="text-[11px] leading-relaxed text-mute">
            手机快捷指令里填的是<strong className="text-frost/80">密钥本身</strong>。下面二选一：方式一直接生成；方式二只填变量名，真实密钥写在电脑的{" "}
            <span className="font-mono text-frost/70">.env</span> 里（不落进配置文件）。
          </p>
          <div className="soft-inset space-y-2 p-2">
            <p className="text-xs text-frost">方式一 · 内联 token（推荐先测通）</p>
            <p className="text-[11px] text-mute">点「生成」→ 复制密钥到手机 Header → 再点保存。保存后此处不再回显明文。</p>
            <div className="flex gap-1">
              <input
                className="hud-input w-full font-mono text-xs"
                value={draft.token || ""}
                placeholder={draft.token_configured ? "（已配置，不再回显明文）" : "点击生成或粘贴密钥"}
                onChange={(e) => setDraft({ token: e.target.value })}
              />
              <button
                type="button"
                className="hud-btn shrink-0"
                onClick={() => setDraft({ token: genDeviceToken(), token_configured: false })}
              >
                生成
              </button>
            </div>
          </div>
          <div className="soft-inset space-y-2 p-2">
            <p className="text-xs text-frost">方式二 · 环境变量名（进阶，可选）</p>
            <p className="text-[11px] text-mute">
              这里只填<strong className="text-frost/80">变量名</strong>，不是密钥。例如填{" "}
              <span className="font-mono text-frost/70">MAILBUS_DEVICE_TOKEN_PHONE</span>
              ，再在项目根目录 <span className="font-mono text-frost/70">.env</span> 写一行：
              <br />
              <span className="mt-1 inline-block font-mono text-frost/70">MAILBUS_DEVICE_TOKEN_PHONE=你的密钥</span>
              <br />
              改完需重启 mailbus。与方式一都填时，以环境变量为准。
            </p>
            <input
              className="hud-input w-full font-mono text-xs"
              value={draft.token_env}
              placeholder="MAILBUS_DEVICE_TOKEN_PHONE"
              onChange={(e) => setDraft({ token_env: e.target.value })}
            />
          </div>
        </div>

        <label className="block">
          <FieldLabel tip="可选。填手机在 Tailscale 里的 100.x.y.z 地址（可多个，逗号分隔）。配了就只允许这些 IP 访问；留空则只靠 token 鉴权。">
            tailscale_ips
          </FieldLabel>
          <input
            className="hud-input mt-1 w-full font-mono text-xs"
            value={draft.tailscale_ips.join(", ")}
            placeholder="100.x.y.z"
            onChange={(e) =>
              setDraft({
                tailscale_ips: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-mute">
          <input
            type="checkbox"
            checked={draft.enabled !== false}
            onChange={(e) => setDraft({ enabled: e.target.checked })}
          />
          启用此设备
          <FieldHint tip="仅控制这台设备。关掉后该 token 失效，其它设备不受影响。" />
        </label>

        <div className="soft-inset p-2 text-xs text-mute">
          <p className="text-frost/70">快捷指令 URL</p>
          <p className="font-mono">http://&lt;电脑 MagicDNS 或 100.x&gt;:9814/api/device/chat</p>
          <p className="font-mono mt-1">…/api/device/task（建工单，同样设备 token）</p>
          <p className="mt-1">
            Header：<span className="font-mono">Authorization: Bearer &lt;设备token&gt;</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="hud-btn"
            disabled={busy}
            onClick={() => void saveDevice(draft, editIndex)}
          >
            {isCreate ? "保存新设备" : "保存此设备"}
          </button>
          <button type="button" className="hud-btn" disabled={busy} onClick={() => setEditor({ mode: "list" })}>
            取消
          </button>
          {!isCreate && editIndex != null && (
            <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void deleteDevice(editIndex)}>
              删除
            </button>
          )}
          {msg && <p className="text-xs text-amber-signal">{msg}</p>}
        </div>
      </div>
    );
  }

  // ── 列表页：全局设置 + 设备摘要 ──
  return (
    <div className="space-y-4">
      <p className="text-xs text-mute">
        外部设备经 Tailscale 投到绑定 Agent，一轮一答。全局开关与单台设备分开保存；点「添加 / 编辑」进入独立配置页。
      </p>

      <div className="soft-inset space-y-3 p-3">
        <p className="text-sm text-frost">全局设置</p>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 text-sm text-frost">
            <input
              type="checkbox"
              checked={data.enabled}
              onChange={(e) => setData({ ...data, enabled: e.target.checked })}
            />
            启用
            <FieldHint tip="总开关。关闭后所有设备请求都会返回 403。" />
          </label>
          <label className="flex items-center gap-2 text-sm text-frost">
            <input
              type="checkbox"
              checked={data.write_memory}
              onChange={(e) => setData({ ...data, write_memory: e.target.checked })}
            />
            每轮写入 memory
            <FieldHint tip="每轮问答各写一条记忆，防 Agent 失忆。建议开启。" />
          </label>
          <label className="block">
            <FieldLabel tip="同步等待 Agent 回复的毫秒数；超时返回 pending，手机用 ticket 轮询。">
              default_wait_ms
            </FieldLabel>
            <input
              className="hud-input mt-1 w-40 font-mono text-xs"
              type="number"
              value={data.default_wait_ms}
              onChange={(e) => setData({ ...data, default_wait_ms: Number(e.target.value) || 8000 })}
            />
          </label>
        </div>
        <button type="button" className="hud-btn" disabled={busy} onClick={() => void saveGlobal()}>
          保存全局设置
        </button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-frost">绑定设备</p>
          <button
            type="button"
            className="hud-btn"
            onClick={() => {
              setMsg("");
              setEditor({ mode: "create", draft: blankDevice() });
            }}
          >
            + 添加设备
          </button>
        </div>

        {data.devices.length === 0 && <p className="text-xs text-mute">尚未配置设备，点右上角添加</p>}

        {data.devices.map((d, idx) => (
          <div key={`${d.id}-${idx}`} className="soft-inset flex flex-wrap items-center justify-between gap-2 p-3">
            <div className="min-w-0 space-y-0.5">
              <p className="truncate text-sm text-frost">
                {d.label || d.id}
                <span className="ml-2 font-mono text-[11px] text-mute">{d.id}</span>
              </p>
              <p className="text-xs text-mute">
                → <span className="font-mono text-frost/80">{d.agent_id || "（未绑 Agent）"}</span>
                {" · "}
                <span className={d.token_configured ? "text-mint" : "text-amber-signal"}>
                  {d.token_configured ? "token 已配置" : "token 未配置"}
                </span>
                {" · "}
                {d.enabled === false ? "已停用" : "启用中"}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="hud-btn"
                onClick={() => {
                  setMsg("");
                  setEditor({ mode: "edit", index: idx, draft: { ...d, token: d.token || "", token_env: d.token_env || "", tailscale_ips: [...(d.tailscale_ips || [])] } });
                }}
              >
                编辑
              </button>
              <button type="button" className="hud-btn-amber" disabled={busy} onClick={() => void deleteDevice(idx)}>
                删除
              </button>
            </div>
          </div>
        ))}
      </div>

      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
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
    <div className="soft-panel space-y-4">
      <div className="space-y-1">
        <p className="soft-panel-title">运维</p>
        <p className="text-xs text-mute">低频维护操作：同步花名册 · 迁移角色框架 · 扫描发现</p>
      </div>

      <section className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <p className="text-sm text-frost">Align store · 同步花名册</p>
            <p className="text-xs text-mute">把种子/SoT 配置合并进 store，补齐新增的 agent 与 framework 段</p>
          </div>
          <button type="button" className="hud-btn shrink-0" disabled={busy} onClick={() => void align()}>
            Align store
          </button>
        </div>
        {alignOut != null && (
          <pre className="max-h-40 overflow-auto rounded bg-black/20 p-2 text-xs text-mute">{JSON.stringify(alignOut, null, 2)}</pre>
        )}
      </section>

      <section className="space-y-2 border-t border-white/[0.06] pt-3">
        <div className="space-y-0.5">
          <p className="text-sm text-frost">Transfer · 迁移角色框架</p>
          <p className="text-xs text-mute">把一个角色从当前 framework 迁到另一个（迁移 inbox 未读、归档记忆、默认停用）</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="hud-label">agent_id（角色 ID）</span>
            <input
              className="hud-input mt-1 w-40"
              value={agentId}
              placeholder="如 agent-a"
              onChange={(e) => setAgentId(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="hud-label">to_framework（目标框架）</span>
            <input
              className="hud-input mt-1 w-40"
              value={toFramework}
              placeholder="如 claude_code / codex"
              onChange={(e) => setToFramework(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-mute">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            dry_run（预览，不落盘）
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
      </section>

      <section className="space-y-2 border-t border-white/[0.06] pt-3">
        <div className="space-y-0.5">
          <p className="text-sm text-frost">Discover · 扫描发现</p>
          <p className="text-xs text-mute">扫描文件系统发现 agent，可逐个启用 / 停用</p>
        </div>
        <DiscoverPage compact />
      </section>

      {msg && <p className="text-xs text-amber-signal">{msg}</p>}
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
        <span className="text-amber-signal">提示</span>：默认所有写 API 需要 Bearer
        Token（本机也不再免鉴权）。Token 存在后端 <code className="font-mono">store/secrets.json</code>（或
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

/** Settings surface for cockpit knobs + gear. `full` = hub composing the same panels. */
export function ConfigPage({ variant = "full" }: { variant?: ConfigVariant }) {
  // llm 历史别名 → agent（舰桥模型旋钮）
  const v: ConfigVariant = variant === "llm" ? "agent" : variant;

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
        <SoftFold title="无 Token 写白名单" hint="默认关闭 · CIDR 可含 WSL/虚拟机 · CORS">
          <AuthSecurityPanel />
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
            <SoftFold title="运维" hint="同步花名册 · 迁移角色 · 扫描发现">
              <AgentOpsPanel />
            </SoftFold>
          </div>
          <div className="space-y-3">
            <SoftFold title="智能体实例 / 角色" hint="实例卡 · 加载角色 · 配置">
              <AgentRuntimePanel />
            </SoftFold>
            <SoftFold title="框架运行时" hint="frameworks · Codex · Claude">
              <RuntimeFrameworkPanel />
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
        <SoftFold title="调度 / Intake / 自动化" hint="scheduler · intake_bridge · verify">
          <BusOpsPanel />
        </SoftFold>
        <SoftFold title="路由 / 端口" hint="workflow · chains · launch_ports">
          <BusRoutesPanel />
        </SoftFold>
        <SoftFold title="工作流注册表" hint="只读浏览 / 轻量编辑 · /api/workflows">
          <WorkflowBoardPage />
        </SoftFold>
        <SoftFold title="Compose YAML" hint="加载/编辑/保存 · 不含启停">
          <ComposeFilesPanel />
        </SoftFold>
        <SoftFold title="外接设备桥" hint="设备 token 鉴权 · 一轮一答 · 与工单隔离">
          <DeviceBridgePanel />
        </SoftFold>
      </div>
    );
  }

  // full = 驾驶舱三旋钮合页（agent + bus + gear），不再另起「全部 sections」心智
  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Settings hub</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide text-frost">配置合页</h2>
        <p className="mt-1 text-sm text-mute">
          与舰桥「智能体 / 总线 / 齿轮」同面板；旧路由 <code className="font-mono">/config</code> 保留
        </p>
      </header>
      <SoftFold title="齿轮 · API / Token / 鉴权" hint="与舰桥 Gear 一致" defaultOpen>
        <GearPanel />
        <div className="mt-3">
          <AuthSecurityPanel />
        </div>
      </SoftFold>
      <SoftFold title="智能体 · 模型 / 实例 / 框架运行时" hint="与舰桥 Agent 一致">
        <ModelConfigPanel filter="provider" />
        <ModelConfigPanel filter="routing" />
        <ModelConfigPanel filter="internal" />
        <ModelConfigPanel filter="services" />
        <div className="mt-3">
          <AgentRuntimePanel />
        </div>
        <div className="mt-3">
          <RuntimeFrameworkPanel />
        </div>
        <div className="mt-3">
          <AgentOpsPanel />
        </div>
      </SoftFold>
      <SoftFold title="总线 · 资产 / Compose / 设备 / 调度" hint="与舰桥 Bus 一致">
        <AssetPathsPanel />
        <div className="mt-3">
          <BusExtrasPanel />
        </div>
        <SoftFold title="调度 / Intake / 自动化">
          <BusOpsPanel />
        </SoftFold>
        <SoftFold title="路由 / 端口">
          <BusRoutesPanel />
        </SoftFold>
        <SoftFold title="工作流注册表" hint="只读浏览 / 轻量编辑">
          <WorkflowBoardPage />
        </SoftFold>
        <SoftFold title="Compose YAML" hint="加载/编辑/保存 · 不含启停">
          <ComposeFilesPanel />
        </SoftFold>
        <SoftFold title="外接设备桥">
          <DeviceBridgePanel />
        </SoftFold>
      </SoftFold>
      <SoftFold title="技能源 / 发现" hint="legacy 合页附加">
        <SkillsSourceView />
        <div className="mt-3">
          <DiscoverPage />
        </div>
      </SoftFold>
    </div>
  );
}
