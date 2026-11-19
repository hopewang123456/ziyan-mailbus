import { type FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 员工与入伙审核：pending 通过后直接激活；active 含心跳离线的人。 */

type StaffRow = {
  employee_id: string;
  display_name: string;
  account_type: string;
  status: string;
  team_id?: string | null;
  position_id?: string | null;
  seat_id?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_framework?: string | null;
  capabilities: string[];
  endpoint?: string | null;
  endpoint_approved: boolean;
  last_heartbeat?: string | null;
};

type AgentOption = {
  agent_id: string;
  name: string;
  framework: string;
  enabled: boolean;
};

type InviteOut = {
  invite_code: string;
  account_type: string;
  data_scope: string;
  capabilities: string[];
  team_id?: string | null;
  position_id?: string | null;
  expires_at?: string | null;
};

type TeamOption = { team_id: string; name: string };
type PositionOption = { position_id: string; name: string };

const INVITE_CAPABILITIES = [
  "message_send",
  "message_read",
  "task_create",
  "task_dispatch",
  "result_submit",
  "hitl_request",
  "hitl_resolve",
  "workflow_create",
  "workflow_modify",
  "employee_invite",
  "employee_remove",
  "agent_deregister",
  "log_read",
  "org_manage",
  "console_admin",
];

type Tab = "pending" | "active" | "all";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "pending", label: "待审核" },
  { key: "active", label: "在职" },
  { key: "all", label: "全部" },
];

const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "default"> = {
  active: "ok",
  offline: "warn",
  pending: "warn",
  deregistered: "danger",
};

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isManager(row: StaffRow) {
  return row.capabilities.includes("console_admin");
}

export function ConsoleStaffApplyPage() {
  const [params] = useSearchParams();
  const inviteCode = (params.get("invite") ?? "").trim().toUpperCase();
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");
  const [employee, setEmployee] = useState<{ employee_id: string; status: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErr("");
    if (!displayName.trim()) {
      setErr("请输入显示名称");
      return;
    }
    setSubmitting(true);
    const result = await api<{ employee: { employee_id: string; status: string } }>(
      "/api/identity/staff",
      {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName.trim(),
          account_type: "human",
          ...(inviteCode ? { invite_code: inviteCode } : {}),
        }),
      },
    );
    setSubmitting(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setEmployee(result.data.employee);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-abyss px-6 py-10 text-frost">
      <div className="w-full max-w-md rounded-lg border border-rail bg-hull/60 p-6">
        <h1 className="font-display text-xl">员工入伙申请</h1>
        <p className="mt-2 text-xs leading-relaxed text-mute">
          提交后等待管理员审核并激活；员工 Token 由管理员在激活后一次性交付。
        </p>
        {inviteCode ? (
          <p className="mt-3 rounded border border-mint/40 bg-mint/5 px-3 py-2 text-xs text-mint">
            已携带邀请码 <span className="font-mono">{inviteCode}</span>
            ，提交后将按邀请授予的团队/能力进入审核。
          </p>
        ) : null}
        {employee ? (
          <div className="mt-6 rounded border border-mint/40 bg-mint/5 p-4 text-xs">
            <p className="text-mint">申请已提交，请等待管理员审核。</p>
            <p className="mt-3 text-mute">申请编号</p>
            <p className="mt-1 break-all font-mono text-frost">{employee.employee_id}</p>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
            <label className="block text-xs text-mute">
              显示名称
              <input
                className="mt-1 block w-full rounded border border-rail bg-hull px-3 py-2 text-sm text-frost"
                value={displayName}
                maxLength={64}
                autoFocus
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
            {err && <p className="text-xs text-flare">{err}</p>}
            <button type="submit" className="hud-btn w-full text-xs" disabled={submitting}>
              {submitting ? "提交中…" : "提交申请"}
            </button>
          </form>
        )}
        <div className="mt-6 flex gap-4 text-xs text-mute">
          <a href="/console" className="hover:text-frost">管理员登录</a>
          <a href="/console" className="hover:text-frost">返回管理中心</a>
        </div>
      </div>
    </main>
  );
}

export function ConsoleStaffPage({
  superAdmin = false,
  can,
}: {
  superAdmin?: boolean;
  can?: (capability: string) => boolean;
}) {
  const allowed = (capability: string) => superAdmin || can?.(capability) === true;
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<StaffRow[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [seatDrafts, setSeatDrafts] = useState<Record<string, string>>({});
  const [agentDrafts, setAgentDrafts] = useState<Record<string, string>>({});
  const [reasonDrafts, setReasonDrafts] = useState<Record<string, string>>({});
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [positions, setPositions] = useState<PositionOption[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteCaps, setInviteCaps] = useState<string[]>([]);
  const [inviteForm, setInviteForm] = useState({
    account_type: "human",
    team_id: "",
    position_id: "",
    data_scope: "self",
    expires_in_hours: "72",
  });
  const [invite, setInvite] = useState<InviteOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [issuedToken, setIssuedToken] = useState<{ name: string; token: string } | null>(null);

  const load = async (status: Tab) => {
    setLoading(true);
    const result = await api<StaffRow[]>(`/api/identity/staff?status=${status}`);
    setLoading(false);
    if (result.ok) {
      setRows(result.data);
      setSeatDrafts({});
      setAgentDrafts({});
      setReasonDrafts({});
      setErr("");
    } else {
      setRows([]);
      setErr(result.error);
    }
  };

  useEffect(() => {
    void load(tab);
  }, [tab]);

  // Agent 台账用于员工绑定下拉；接口不可用时只展示已有绑定
  useEffect(() => {
    void api<AgentOption[]>("/api/agents").then((result) => {
      if (result.ok && Array.isArray(result.data)) setAgents(result.data);
    });
    void Promise.all([
      api<TeamOption[]>("/api/org/teams"),
      api<PositionOption[]>("/api/org/positions"),
    ]).then(([teamRes, positionRes]) => {
      if (teamRes.ok && Array.isArray(teamRes.data)) setTeams(teamRes.data);
      if (positionRes.ok && Array.isArray(positionRes.data)) setPositions(positionRes.data);
    });
  }, []);

  async function approve(row: StaffRow) {
    setMsg("");
    setErr("");
    const path = `/api/identity/staff/${encodeURIComponent(row.employee_id)}`;
    const reviewed = await api(`${path}/review`, {
      method: "POST",
      body: JSON.stringify({ approved: true }),
    });
    if (!reviewed.ok) {
      setErr(reviewed.error);
      return;
    }
    const activated = await api<{ token: string }>(`${path}/activate`, { method: "POST" });
    if (!activated.ok) {
      setErr(activated.error);
      return;
    }
    setIssuedToken({ name: row.display_name, token: activated.data.token });
    setMsg(`已通过并激活「${row.display_name}」，请立即交付员工 Token`);
    await load(tab);
  }

  async function reject(row: StaffRow) {
    setMsg("");
    setErr("");
    const result = await api(
      `/api/identity/staff/${encodeURIComponent(row.employee_id)}/review`,
      {
        method: "POST",
        body: JSON.stringify({ approved: false, note: "审核未通过" }),
      },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已驳回「${row.display_name}」`);
    await load(tab);
  }

  async function mutate(row: StaffRow, action: string, body: unknown, okMsg: string) {
    setMsg("");
    setErr("");
    const result = await api(
      `/api/identity/staff/${encodeURIComponent(row.employee_id)}/${action}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(okMsg);
    await load(tab);
  }

  const saveSeat = (row: StaffRow) => {
    const draft = seatDrafts[row.employee_id] ?? row.seat_id ?? "";
    const seatId = draft.trim();
    void mutate(
      row,
      "seat",
      { seat_id: seatId || null },
      seatId ? `已将「${row.display_name}」安排到 ${seatId}` : `已释放「${row.display_name}」的工位`,
    );
  };

  const saveAgent = (row: StaffRow) => {
    const agentId = (agentDrafts[row.employee_id] ?? row.agent_id ?? "").trim();
    void mutate(
      row,
      "agent",
      { agent_id: agentId || null },
      agentId
        ? `已将「${row.display_name}」绑定到 ${agentId}`
        : `已解除「${row.display_name}」的 Agent 绑定`,
    );
  };

  const inviteLink = invite
    ? `${window.location.origin}/join?invite=${encodeURIComponent(invite.invite_code)}`
    : "";

  async function createInvite() {
    setErr("");
    setMsg("");
    const expires = Number(inviteForm.expires_in_hours);
    const result = await api<InviteOut>("/api/identity/invites", {
      method: "POST",
      body: JSON.stringify({
        account_type: inviteForm.account_type,
        team_id: inviteForm.team_id || null,
        position_id: inviteForm.position_id || null,
        data_scope: inviteForm.data_scope,
        expires_in_hours: Number.isFinite(expires) && expires > 0 ? Math.min(720, expires) : 72,
        capabilities: inviteCaps,
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setInvite(result.data);
    setMsg("邀请已生成，请复制链接发给对方");
  }

  /** 离职注销：后端会同时清空工位，释放后立即可再分配。 */
  async function dismiss(row: StaffRow) {
    setMsg("");
    setErr("");
    const reason = (reasonDrafts[row.employee_id] ?? "").trim() || "离职";
    const result = await api(
      `/api/identity/staff/${encodeURIComponent(row.employee_id)}/deregister`,
      { method: "POST", body: JSON.stringify({ reason }) },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(
      row.seat_id
        ? `已注销「${row.display_name}」，工位 ${row.seat_id} 已释放`
        : `已注销「${row.display_name}」`,
    );
    await load(tab);
  }

  return (
    <>
      <ConsolePageHeader
        title="员工与入伙审核"
        description="入伙审核、激活与在职状态；超管可绑定 Agent、分配工位、审核端点、指定管理者；注销离职时工位自动释放"
        actions={
          allowed("employee_invite") ? (
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => setInviteOpen((value) => !value)}
            >
              {inviteOpen ? "收起邀请" : "生成邀请链接"}
            </button>
          ) : undefined
        }
      />

      {inviteOpen && allowed("employee_invite") && (
        <ConsoleSection title="邀请入伙">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-mute">
              账号类型
              <select
                className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={inviteForm.account_type}
                onChange={(e) => setInviteForm({ ...inviteForm, account_type: e.target.value })}
              >
                <option value="human">human · 人</option>
                <option value="agent">agent · Agent</option>
              </select>
            </label>
            <label className="text-[11px] text-mute">
              团队
              <select
                className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={inviteForm.team_id}
                onChange={(e) => setInviteForm({ ...inviteForm, team_id: e.target.value })}
              >
                <option value="">不预置</option>
                {teams.map((team) => (
                  <option key={team.team_id} value={team.team_id}>
                    {team.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-[11px] text-mute">
              岗位
              <select
                className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={inviteForm.position_id}
                onChange={(e) => setInviteForm({ ...inviteForm, position_id: e.target.value })}
              >
                <option value="">不预置</option>
                {positions.map((position) => (
                  <option key={position.position_id} value={position.position_id}>
                    {position.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-[11px] text-mute">
              数据范围
              <select
                className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={inviteForm.data_scope}
                onChange={(e) => setInviteForm({ ...inviteForm, data_scope: e.target.value })}
              >
                <option value="self">self</option>
                <option value="team">team</option>
                <option value="global">global</option>
              </select>
            </label>
            <label className="text-[11px] text-mute">
              有效期（小时）
              <input
                type="number"
                min={1}
                max={720}
                className="mt-1 block w-24 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={inviteForm.expires_in_hours}
                onChange={(e) =>
                  setInviteForm({ ...inviteForm, expires_in_hours: e.target.value })
                }
              />
            </label>
            <button type="button" className="hud-btn text-xs" onClick={() => void createInvite()}>
              生成邀请码
            </button>
          </div>

          <div className="mt-3">
            <p className="mb-1.5 text-[10px] uppercase tracking-widest text-mute">邀请授予能力</p>
            <div className="flex flex-wrap gap-1.5">
              {INVITE_CAPABILITIES.map((capability) => {
                const active = inviteCaps.includes(capability);
                return (
                  <button
                    key={capability}
                    type="button"
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      active
                        ? "border-mint/50 bg-mint/10 text-mint"
                        : "border-rail text-mute hover:text-frost"
                    }`}
                    onClick={() =>
                      setInviteCaps((prev) =>
                        active
                          ? prev.filter((item) => item !== capability)
                          : [...prev, capability],
                      )
                    }
                  >
                    {capability}
                  </button>
                );
              })}
            </div>
          </div>

          {invite && (
            <div className="mt-4 rounded border border-mint/40 bg-mint/5 p-3">
              <p className="text-xs text-mint">邀请已生成，有效期至 {timeText(invite.expires_at)}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  readOnly
                  className="min-w-0 flex-1 rounded border border-rail bg-hull px-2 py-1 font-mono text-xs text-frost"
                  value={inviteLink}
                  onFocus={(event) => event.currentTarget.select()}
                />
                <button
                  type="button"
                  className="hud-btn text-xs"
                  onClick={() => {
                    if (!navigator.clipboard) {
                      setErr("当前浏览器不支持自动复制，请选中链接手动复制");
                      return;
                    }
                    void navigator.clipboard.writeText(inviteLink).then(
                      () => setMsg("邀请链接已复制"),
                      () => setErr("复制失败，请选中链接手动复制"),
                    );
                  }}
                >
                  复制链接
                </button>
              </div>
              <p className="mt-2 text-[11px] text-mute">
                邀请码 <span className="font-mono text-frost">{invite.invite_code}</span> · 能力{" "}
                {invite.capabilities.length ? invite.capabilities.join(", ") : "无"}
              </p>
            </div>
          )}
        </ConsoleSection>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`rounded border px-2.5 py-1 text-xs ${
              tab === item.key
                ? "border-mint/50 bg-mint/10 text-mint"
                : "border-rail text-mute hover:text-frost"
            }`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
        <button
          type="button"
          className="ml-auto rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost"
          onClick={() => void load(tab)}
        >
          刷新
        </button>
      </div>

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      {issuedToken && (
        <ConsoleSection
          title={`员工 Token：${issuedToken.name}（仅本次显示）`}
          actions={
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
              onClick={() => setIssuedToken(null)}
            >
              已交付，关闭
            </button>
          }
        >
          <p className="mb-2 text-xs text-amber-signal">
            此 Token 无法通过重复激活找回，请复制并安全交付给员工；不会覆盖当前管理员登录。
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              readOnly
              className="min-w-0 flex-1 rounded border border-rail bg-hull px-2 py-1 font-mono text-xs text-frost"
              value={issuedToken.token}
              onFocus={(event) => event.currentTarget.select()}
            />
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => {
                if (!navigator.clipboard) {
                  setErr("当前浏览器不支持自动复制，请选中 Token 手动复制");
                  return;
                }
                void navigator.clipboard.writeText(issuedToken.token).then(
                  () => setMsg("员工 Token 已复制"),
                  () => setErr("复制失败，请选中 Token 手动复制"),
                );
              }}
            >
              复制 Token
            </button>
          </div>
        </ConsoleSection>
      )}

      <ConsoleSection title={`员工（${rows.length}）`}>
        <ConsoleTable
          rows={rows}
          rowKey={(row) => row.employee_id}
          loading={loading}
          empty="暂无员工"
          columns={[
            { key: "name", header: "姓名", render: (row) => row.display_name },
            {
              key: "type",
              header: "类型",
              render: (row) => <ConsoleTag>{row.account_type}</ConsoleTag>,
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <ConsoleTag tone={STATUS_TONE[row.status] || "default"}>
                  {row.status}
                </ConsoleTag>
              ),
            },
            {
              key: "agent",
              header: "Agent",
              render: (row) =>
                row.status === "deregistered" ? (
                  <span className="font-mono text-[11px]">{row.agent_name || "—"}</span>
                ) : (
                  <span className="flex flex-col gap-1">
                    <span className="text-[11px]">
                      {row.agent_name || <span className="text-mute">未绑定</span>}
                      {row.agent_framework ? (
                        <span className="ml-1 text-mute">· {row.agent_framework}</span>
                      ) : null}
                    </span>
                    {superAdmin ? (
                      <span className="flex items-center gap-1">
                        <select
                          className="w-36 rounded border border-rail bg-hull px-1.5 py-0.5 text-[11px] text-frost"
                          value={agentDrafts[row.employee_id] ?? row.agent_id ?? ""}
                          onChange={(e) =>
                            setAgentDrafts((prev) => ({
                              ...prev,
                              [row.employee_id]: e.target.value,
                            }))
                          }
                        >
                          <option value="">未绑定</option>
                          {agents.map((agent) => (
                            <option key={agent.agent_id} value={agent.agent_id}>
                              {agent.name} · {agent.framework}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="rounded border border-rail px-1.5 py-0.5 text-[11px] text-mute hover:text-frost"
                          onClick={() => saveAgent(row)}
                        >
                          保存
                        </button>
                      </span>
                    ) : null}
                  </span>
                ),
            },
            {
              key: "team",
              header: "团队 / 岗位",
              render: (row) => (
                <span className="font-mono text-[11px] text-mute">
                  {row.team_id || "—"} / {row.position_id || "—"}
                </span>
              ),
            },
            {
              key: "seat",
              header: "工位",
              render: (row) =>
                row.status === "deregistered" ? (
                  <span className="font-mono text-[11px]">{row.seat_id || "—"}</span>
                ) : (
                  <span className="flex items-center gap-1">
                    <input
                      className="w-24 rounded border border-rail bg-hull px-1.5 py-0.5 font-mono text-[11px] text-frost"
                      placeholder="seat_id"
                      disabled={!allowed("org_manage")}
                      value={seatDrafts[row.employee_id] ?? row.seat_id ?? ""}
                      onChange={(e) =>
                        setSeatDrafts((prev) => ({
                          ...prev,
                          [row.employee_id]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveSeat(row);
                      }}
                    />
                    <button
                      type="button"
                      className="rounded border border-rail px-1.5 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                      disabled={!allowed("org_manage")}
                      onClick={() => saveSeat(row)}
                    >
                      保存
                    </button>
                  </span>
                ),
            },
            ...(superAdmin
              ? [
                  {
                    key: "endpoint",
                    header: "端点审核",
                    render: (row: StaffRow) =>
                      row.account_type !== "agent" || !row.endpoint ? (
                        <span className="text-[11px] text-mute">—</span>
                      ) : (
                        <button
                          type="button"
                          className="rounded border border-rail px-1.5 py-0.5 text-[11px]"
                          onClick={() =>
                            void mutate(
                              row,
                              "endpoint",
                              { approved: !row.endpoint_approved },
                              row.endpoint_approved
                                ? `已撤销「${row.display_name}」的端点审核`
                                : `已通过「${row.display_name}」的端点审核`,
                            )
                          }
                        >
                          <ConsoleTag tone={row.endpoint_approved ? "ok" : "warn"}>
                            {row.endpoint_approved ? "已通过" : "待审核"}
                          </ConsoleTag>
                        </button>
                      ),
                  },
                  {
                    key: "manager",
                    header: "管理员",
                    render: (row: StaffRow) =>
                      row.capabilities.includes("*") ? (
                        <ConsoleTag tone="ok">超管</ConsoleTag>
                      ) : (
                        <button
                          type="button"
                          className="rounded border border-rail px-1.5 py-0.5 text-[11px] text-mute hover:text-frost"
                          disabled={row.status === "deregistered"}
                          onClick={() =>
                            void mutate(
                              row,
                              "manager",
                              { enabled: !isManager(row) },
                              isManager(row)
                                ? `已取消「${row.display_name}」的管理者资格`
                                : `已将「${row.display_name}」设为管理者`,
                            )
                          }
                        >
                          {isManager(row) ? "取消管理者" : "设为管理者"}
                        </button>
                      ),
                  },
                ]
              : []),
            {
              key: "caps",
              header: "能力",
              render: (row) => (
                <span className="text-mute">
                  {row.capabilities.slice(0, 3).join(", ") || "—"}
                  {row.capabilities.length > 3 ? ` +${row.capabilities.length - 3}` : ""}
                </span>
              ),
            },
            {
              key: "hb",
              header: "最近心跳",
              render: (row) => (
                <span className="text-[11px] text-mute">{timeText(row.last_heartbeat)}</span>
              ),
            },
            {
              key: "act",
              header: "操作",
              render: (row) =>
                row.status === "pending" ? (
                  <span className="flex gap-1.5">
                    <button
                      type="button"
                      className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
                      disabled={!allowed("employee_invite")}
                      onClick={() => void approve(row)}
                    >
                      通过并激活
                    </button>
                    <button
                      type="button"
                      className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                      disabled={!allowed("employee_invite")}
                      onClick={() => void reject(row)}
                    >
                      驳回
                    </button>
                  </span>
                ) : superAdmin && row.status !== "deregistered" ? (
                  <span className="flex items-center gap-1.5">
                    <input
                      className="w-24 rounded border border-rail bg-hull px-1.5 py-0.5 text-[11px] text-frost"
                      placeholder="离职原因"
                      value={reasonDrafts[row.employee_id] ?? ""}
                      onChange={(e) =>
                        setReasonDrafts((prev) => ({
                          ...prev,
                          [row.employee_id]: e.target.value,
                        }))
                      }
                    />
                    <button
                      type="button"
                      className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
                      onClick={() => void dismiss(row)}
                    >
                      注销
                    </button>
                  </span>
                ) : (
                  <span className="text-mute">—</span>
                ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
