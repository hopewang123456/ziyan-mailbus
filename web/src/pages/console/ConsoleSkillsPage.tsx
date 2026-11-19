import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/**
 * 技能包管理：包 / 版本 / 来源 / 启停 / 绑定 / 有效技能预览。
 * 契约：GET/POST /api/skills、PATCH /api/skills/{id}、POST refresh / delete / bindings、
 *       GET /api/skills/effective?target_type=&target_id=
 */

type SourceType = "local" | "http";

type SkillBinding = {
  target_type: "agent" | "employee";
  target_id: string;
  enabled: boolean;
};

type SkillPackage = {
  package_id: string;
  name: string;
  source_type: SourceType;
  source_uri: string;
  entry: string;
  version: string;
  enabled: boolean;
  note: string;
  bindings: SkillBinding[];
  last_checked_at?: string | null;
  last_error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type EffectiveSkill = {
  package_id: string;
  name: string;
  source_type: string;
  source_uri: string;
  entry: string;
  version: string;
  enabled: boolean;
  note: string;
  origin: string;
};

type AgentRow = { agent_id: string; name: string; framework: string; enabled: boolean };
type StaffRow = { employee_id: string; display_name: string; status: string };

type TargetType = "agent" | "employee";

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const EMPTY_FORM = {
  name: "",
  source_type: "local" as SourceType,
  source_uri: "",
  entry: "SKILL.md",
  note: "",
};

export function ConsoleSkillsPage({ can }: { can: (capability: string) => boolean }) {
  const [packages, setPackages] = useState<SkillPackage[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [staff, setStaff] = useState<StaffRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  // 新建 / 编辑共用一套表单
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  // 绑定
  const [bindPackageId, setBindPackageId] = useState("");
  const [bindTargetType, setBindTargetType] = useState<TargetType>("agent");
  const [bindTargetId, setBindTargetId] = useState("");

  // 有效技能预览
  const [effTargetType, setEffTargetType] = useState<TargetType>("agent");
  const [effTargetId, setEffTargetId] = useState("");
  const [effective, setEffective] = useState<EffectiveSkill[]>([]);
  const [effectiveLoaded, setEffectiveLoaded] = useState(false);

  const canManage = can("system_config");

  const load = async () => {
    setLoading(true);
    const [pkgRes, agentRes, staffRes] = await Promise.all([
      api<SkillPackage[]>("/api/skills"),
      api<AgentRow[]>("/api/agents"),
      api<StaffRow[]>("/api/identity/staff?status=active"),
    ]);
    setLoading(false);
    const errors: string[] = [];
    if (pkgRes.ok && Array.isArray(pkgRes.data)) setPackages(pkgRes.data);
    else errors.push(pkgRes.ok ? "技能包返回格式异常" : pkgRes.error);
    if (agentRes.ok && Array.isArray(agentRes.data)) setAgents(agentRes.data);
    if (staffRes.ok && Array.isArray(staffRes.data)) setStaff(staffRes.data);
    setErr(errors.join("; "));
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!bindPackageId && packages.length) setBindPackageId(packages[0].package_id);
  }, [packages, bindPackageId]);

  const selectedPackage = useMemo(
    () => packages.find((item) => item.package_id === bindPackageId) ?? null,
    [packages, bindPackageId],
  );

  const enabledCount = packages.filter((item) => item.enabled).length;
  const bindingCount = packages.reduce((sum, item) => sum + item.bindings.length, 0);
  const errorCount = packages.filter((item) => item.last_error).length;

  const targetOptions = effTargetType === "agent" ? agents : staff;

  function targetName(type: TargetType, id: string) {
    if (type === "agent") return agents.find((item) => item.agent_id === id)?.name ?? id;
    return staff.find((item) => item.employee_id === id)?.display_name ?? id;
  }

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function startEdit(pkg: SkillPackage) {
    setEditingId(pkg.package_id);
    setForm({
      name: pkg.name,
      source_type: pkg.source_type,
      source_uri: pkg.source_uri,
      entry: pkg.entry,
      note: pkg.note,
    });
    setMsg("");
    setErr("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submitForm() {
    setErr("");
    setMsg("");
    if (!form.name.trim() || !form.source_uri.trim()) {
      setErr("名称与来源地址必填");
      return;
    }
    const body = {
      name: form.name.trim(),
      source_type: form.source_type,
      source_uri: form.source_uri.trim(),
      entry: form.entry.trim() || "SKILL.md",
      note: form.note.trim(),
    };
    setBusy(true);
    const result = editingId
      ? await api<SkillPackage>(`/api/skills/${encodeURIComponent(editingId)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      : await api<SkillPackage>("/api/skills", {
          method: "POST",
          body: JSON.stringify(body),
        });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(editingId ? `已更新「${result.data.name}」` : `已创建「${result.data.name}」`);
    resetForm();
    await load();
  }

  async function patchPackage(pkg: SkillPackage, body: Record<string, unknown>, okMsg: string) {
    setErr("");
    setMsg("");
    setBusy(true);
    const result = await api<SkillPackage>(
      `/api/skills/${encodeURIComponent(pkg.package_id)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPackages((prev) =>
      prev.map((item) => (item.package_id === pkg.package_id ? result.data : item)),
    );
    setMsg(okMsg);
  }

  async function refreshPackage(pkg: SkillPackage) {
    setErr("");
    setMsg("");
    setBusy(true);
    const result = await api<SkillPackage>(
      `/api/skills/${encodeURIComponent(pkg.package_id)}/refresh`,
      { method: "POST" },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPackages((prev) =>
      prev.map((item) => (item.package_id === pkg.package_id ? result.data : item)),
    );
    setMsg(
      result.data.last_error
        ? `「${pkg.name}」探测失败：${result.data.last_error}`
        : `「${pkg.name}」来源可达，版本 ${result.data.version}`,
    );
  }

  async function deletePackage(pkg: SkillPackage) {
    if (!window.confirm(`确认删除技能包「${pkg.name}」？绑定会一并移除。`)) return;
    setErr("");
    setMsg("");
    setBusy(true);
    const result = await api(`/api/skills/${encodeURIComponent(pkg.package_id)}/delete`, {
      method: "POST",
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已删除「${pkg.name}」`);
    if (editingId === pkg.package_id) resetForm();
    if (bindPackageId === pkg.package_id) setBindPackageId("");
    await load();
  }

  async function saveBinding(pkg: SkillPackage, binding: SkillBinding) {
    setErr("");
    setMsg("");
    setBusy(true);
    const result = await api<SkillPackage>(
      `/api/skills/${encodeURIComponent(pkg.package_id)}/bindings`,
      { method: "POST", body: JSON.stringify(binding) },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPackages((prev) =>
      prev.map((item) => (item.package_id === pkg.package_id ? result.data : item)),
    );
    setMsg(
      `${binding.enabled ? "已启用" : "已停用"}「${pkg.name}」对 ` +
        `${binding.target_type === "agent" ? "Agent" : "员工"} ${targetName(binding.target_type, binding.target_id)} 的绑定`,
    );
  }

  async function addBinding() {
    if (!selectedPackage) {
      setErr("请先选择技能包");
      return;
    }
    if (!bindTargetId) {
      setErr("请选择绑定对象");
      return;
    }
    await saveBinding(selectedPackage, {
      target_type: bindTargetType,
      target_id: bindTargetId,
      enabled: true,
    });
    setBindTargetId("");
  }

  async function loadEffective() {
    setErr("");
    setMsg("");
    if (!effTargetId) {
      setErr("请选择预览对象");
      return;
    }
    setBusy(true);
    const query = `?target_type=${encodeURIComponent(effTargetType)}&target_id=${encodeURIComponent(effTargetId)}`;
    const result = await api<EffectiveSkill[]>(`/api/skills/effective${query}`);
    setBusy(false);
    setEffectiveLoaded(true);
    if (!result.ok || !Array.isArray(result.data)) {
      setEffective([]);
      setErr(result.ok ? "有效技能返回格式异常" : result.error);
      return;
    }
    setEffective(result.data);
  }

  return (
    <>
      <ConsolePageHeader
        title="技能包"
        description="登记本地目录或 HTTP 来源，管理版本、启停与 Agent/员工绑定；来源只探测、不复制文件"
        actions={
          <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
            刷新
          </button>
        }
      />

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "技能包", value: packages.length },
          { label: "已启用", value: enabledCount },
          { label: "绑定", value: bindingCount },
          { label: "来源异常", value: errorCount },
        ].map((item) => (
          <div key={item.label} className="rounded-lg border border-rail bg-hull/60 px-4 py-3">
            <p className="text-[10px] uppercase tracking-widest text-mute">{item.label}</p>
            <p className={`mt-1 font-display text-xl ${item.label === "来源异常" && item.value > 0 ? "text-flare" : "text-frost"}`}>
              {item.value}
            </p>
          </div>
        ))}
      </div>

      <ConsoleSection
        title={editingId ? "编辑技能包" : "新建技能包"}
        actions={
          editingId ? (
            <button
              type="button"
              className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
              onClick={resetForm}
            >
              取消编辑
            </button>
          ) : undefined
        }
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            名称
            <input
              className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={form.name}
              maxLength={64}
              placeholder="例如 A2A 评审"
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </label>
          <label className="text-[11px] text-mute">
            来源类型
            <select
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={form.source_type}
              onChange={(event) =>
                setForm({ ...form, source_type: event.target.value as SourceType })
              }
            >
              <option value="local">本地目录 / 文件</option>
              <option value="http">HTTP(S) URL</option>
            </select>
          </label>
          <label className="flex-1 text-[11px] text-mute">
            来源地址
            <input
              className="mt-1 block w-full min-w-56 rounded border border-rail bg-hull px-2 py-1.5 font-mono text-xs text-frost"
              value={form.source_uri}
              maxLength={512}
              placeholder={
                form.source_type === "local"
                  ? "D:\\vault\\skills\\a2a-review"
                  : "https://example.com/skills/a2a-review"
              }
              onChange={(event) => setForm({ ...form, source_uri: event.target.value })}
            />
          </label>
          <label className="text-[11px] text-mute">
            入口
            <input
              className="mt-1 block w-28 rounded border border-rail bg-hull px-2 py-1.5 font-mono text-xs text-frost"
              value={form.entry}
              maxLength={64}
              onChange={(event) => setForm({ ...form, entry: event.target.value })}
            />
          </label>
          <label className="text-[11px] text-mute">
            备注
            <input
              className="mt-1 block w-44 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={form.note}
              maxLength={512}
              onChange={(event) => setForm({ ...form, note: event.target.value })}
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!canManage || busy}
            onClick={() => void submitForm()}
          >
            {editingId ? "保存修改" : "创建"}
          </button>
        </div>
        {!canManage && (
          <p className="mt-2 text-[11px] text-amber-signal">技能包仅超级管理员可维护</p>
        )}
      </ConsoleSection>

      <ConsoleSection title={`技能包（${packages.length}）`}>
        <ConsoleTable
          rows={packages}
          rowKey={(row) => row.package_id}
          loading={loading}
          empty="还没有技能包，先在上方登记一个来源"
          columns={[
            {
              key: "name",
              header: "名称",
              render: (row) => (
                <span>
                  <span className="text-frost">{row.name}</span>
                  {row.note ? <span className="block text-[10px] text-mute">{row.note}</span> : null}
                </span>
              ),
            },
            {
              key: "source",
              header: "来源",
              render: (row) => (
                <span>
                  <ConsoleTag>{row.source_type}</ConsoleTag>
                  <span className="mt-1 block max-w-64 truncate font-mono text-[10px] text-mute" title={row.source_uri}>
                    {row.source_uri}
                  </span>
                  <span className="text-[10px] text-mute">入口 {row.entry}</span>
                </span>
              ),
            },
            { key: "version", header: "版本", render: (row) => <span className="font-mono text-[11px]">{row.version || "—"}</span> },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <ConsoleTag tone={row.enabled ? "ok" : "default"}>{row.enabled ? "启用" : "停用"}</ConsoleTag>
              ),
            },
            {
              key: "bindings",
              header: "绑定",
              render: (row) => (
                <span className="text-[11px] text-mute">
                  {row.bindings.filter((item) => item.enabled).length}/{row.bindings.length}
                </span>
              ),
            },
            {
              key: "checked",
              header: "最近探测",
              render: (row) => (
                <span className="text-[11px]">
                  <span className="text-mute">{timeText(row.last_checked_at)}</span>
                  {row.last_error ? (
                    <span className="mt-1 block max-w-48 truncate text-flare" title={row.last_error}>
                      {row.last_error}
                    </span>
                  ) : null}
                </span>
              ),
            },
            {
              key: "act",
              header: "操作",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  <MiniButton
                    disabled={!canManage || busy}
                    onClick={() => startEdit(row)}
                  >
                    编辑
                  </MiniButton>
                  <MiniButton
                    disabled={!canManage || busy}
                    onClick={() => {
                      setBindPackageId(row.package_id);
                      setMsg("");
                      setErr("");
                    }}
                  >
                    绑定
                  </MiniButton>
                  <MiniButton disabled={!canManage || busy} onClick={() => void refreshPackage(row)}>
                    刷新
                  </MiniButton>
                  <MiniButton
                    disabled={!canManage || busy}
                    onClick={() =>
                      void patchPackage(
                        row,
                        { enabled: !row.enabled },
                        `已${row.enabled ? "停用" : "启用"}「${row.name}」`,
                      )
                    }
                  >
                    {row.enabled ? "停用" : "启用"}
                  </MiniButton>
                  <MiniButton danger disabled={!canManage || busy} onClick={() => void deletePackage(row)}>
                    删除
                  </MiniButton>
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection
        title="绑定管理"
        actions={
          selectedPackage ? (
            <ConsoleTag>{selectedPackage.name}</ConsoleTag>
          ) : undefined
        }
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            技能包
            <select
              className="mt-1 block w-48 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={bindPackageId}
              onChange={(event) => setBindPackageId(event.target.value)}
            >
              <option value="">选择技能包</option>
              {packages.map((pkg) => (
                <option key={pkg.package_id} value={pkg.package_id}>
                  {pkg.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] text-mute">
            对象类型
            <select
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={bindTargetType}
              onChange={(event) => {
                setBindTargetType(event.target.value as TargetType);
                setBindTargetId("");
              }}
            >
              <option value="agent">Agent 默认</option>
              <option value="employee">员工（角色覆盖）</option>
            </select>
          </label>
          <label className="text-[11px] text-mute">
            绑定对象
            <select
              className="mt-1 block w-56 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={bindTargetId}
              onChange={(event) => setBindTargetId(event.target.value)}
            >
              <option value="">选择{bindTargetType === "agent" ? " Agent" : "员工"}</option>
              {bindTargetType === "agent"
                ? agents.map((agent) => (
                    <option key={agent.agent_id} value={agent.agent_id}>
                      {agent.name} · {agent.agent_id}
                    </option>
                  ))
                : staff.map((person) => (
                    <option key={person.employee_id} value={person.employee_id}>
                      {person.display_name} · {person.employee_id}
                    </option>
                  ))}
            </select>
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!canManage || busy || !selectedPackage}
            onClick={() => void addBinding()}
          >
            添加绑定
          </button>
        </div>

        {selectedPackage && selectedPackage.bindings.length > 0 ? (
          <div className="mt-3 space-y-1.5">
            {selectedPackage.bindings.map((binding) => (
              <div
                key={`${binding.target_type}-${binding.target_id}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-rail bg-hull/40 px-3 py-2 text-xs"
              >
                <span className="flex flex-wrap items-center gap-2">
                  <ConsoleTag tone={binding.target_type === "agent" ? "ok" : "warn"}>
                    {binding.target_type === "agent" ? "Agent 默认" : "员工覆盖"}
                  </ConsoleTag>
                  <span className="text-frost">{targetName(binding.target_type, binding.target_id)}</span>
                  <span className="font-mono text-[10px] text-mute">{binding.target_id}</span>
                  <ConsoleTag tone={binding.enabled ? "ok" : "default"}>
                    {binding.enabled ? "生效" : "停用"}
                  </ConsoleTag>
                </span>
                <MiniButton
                  disabled={!canManage || busy}
                  onClick={() =>
                    void saveBinding(selectedPackage, {
                      ...binding,
                      enabled: !binding.enabled,
                    })
                  }
                >
                  {binding.enabled ? "停用" : "启用"}
                </MiniButton>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-mute">该技能包还没有绑定；未绑定时只作为可复用包存在。</p>
        )}
      </ConsoleSection>

      <ConsoleSection title="有效技能预览">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            对象类型
            <select
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={effTargetType}
              onChange={(event) => {
                setEffTargetType(event.target.value as TargetType);
                setEffTargetId("");
                setEffective([]);
                setEffectiveLoaded(false);
              }}
            >
              <option value="agent">Agent</option>
              <option value="employee">员工</option>
            </select>
          </label>
          <label className="text-[11px] text-mute">
            对象
            <select
              className="mt-1 block w-64 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
              value={effTargetId}
              onChange={(event) => setEffTargetId(event.target.value)}
            >
              <option value="">选择对象</option>
              {targetOptions.map((item) => {
                const id = "agent_id" in item ? item.agent_id : item.employee_id;
                const name = "name" in item ? item.name : item.display_name;
                return (
                  <option key={id} value={id}>
                    {name} · {id}
                  </option>
                );
              })}
            </select>
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={busy || !effTargetId}
            onClick={() => void loadEffective()}
          >
            查询有效技能
          </button>
        </div>

        {effectiveLoaded && (
          <div className="mt-3">
            <ConsoleTable
              rows={effective}
              rowKey={(row) => `${row.package_id}-${row.origin}`}
              loading={false}
              empty="该对象没有解析到有效技能"
              columns={[
                { key: "name", header: "技能", render: (row) => row.name },
                {
                  key: "origin",
                  header: "来源层级",
                  render: (row) => <ConsoleTag tone={row.origin.includes("employee") ? "warn" : "ok"}>{row.origin}</ConsoleTag>,
                },
                { key: "version", header: "版本", render: (row) => <span className="font-mono text-[11px]">{row.version || "—"}</span> },
                { key: "entry", header: "入口", render: (row) => <span className="font-mono text-[10px] text-mute">{row.entry}</span> },
                { key: "uri", header: "来源", render: (row) => <span className="block max-w-64 truncate font-mono text-[10px] text-mute" title={row.source_uri}>{row.source_uri}</span> },
              ]}
            />
          </div>
        )}
      </ConsoleSection>
    </>
  );
}

function MiniButton({
  children,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      className={`rounded border px-2 py-0.5 text-[11px] disabled:opacity-40 ${
        danger
          ? "border-flare/50 text-flare hover:bg-flare/10"
          : "border-rail text-mute hover:text-frost"
      }`}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
