import { useCallback, useEffect, useState } from "react";
import { ConsoleDrawer } from "../../components/console/ConsoleDrawer";
import { ConfirmDialog } from "../../components/console/ConsoleDialog";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { ConsoleTabs, useTabParam } from "../../components/console/ConsoleTabs";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import {
  createPosition,
  createRole,
  createTeam,
  deleteEmployee,
  deletePosition,
  deleteRole,
  deleteTeam,
  getEmployeeCapabilities,
  getEmployeePermissions,
  getEmployeeRoles,
  inviteEmployee,
  listTeamSeats,
  putEmployeeCapabilities,
  putEmployeePermissions,
  putEmployeeRoles,
  updateEmployee,
  updatePosition,
  updateRole,
  updateTeam,
  assignSeat,
} from "../../lib/org/api";
import { useEmployees, usePositions, useRoles, useTeams } from "../../lib/org/hooks";
import {
  ACCOUNT_TYPE_LABELS,
  DATA_SCOPE_LABEL,
  EMPLOYEE_STATUS_LABELS,
  mapEmployee,
} from "../../lib/org/view";
import type {
  EmployeeRow,
  PositionRow,
  RoleRow,
  TeamRow,
} from "../../lib/org/view";
import {
  ALL_PERMISSIONS,
  PERMISSION_GROUPS,
  PERMISSION_LABELS,
} from "../../lib/permissions";

const TABS = ["staff", "positions", "roles", "teams"] as const;
const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  staff: "员工",
  positions: "岗位",
  roles: "角色",
  teams: "团队",
};

export interface ConsoleOrganizationPageProps {
  can: (capability: string) => boolean;
}

// ──────────────────────────────────────────────────────────────
// 主入口
// ──────────────────────────────────────────────────────────────
export function ConsoleOrganizationPage({ can }: ConsoleOrganizationPageProps) {
  const [tab, setTab] = useTabParam(TABS, "staff");

  return (
    <>
      <ConsolePageHeader
        title="组织"
        description="员工 / 岗位 / 角色 / 团队"
      />
      <ConsoleTabs
        tabs={TABS.map((key) => ({ key, label: TAB_LABELS[key] }))}
        value={tab}
        onChange={setTab}
      />
      {tab === "staff" && <StaffTab can={can} />}
      {tab === "positions" && <PositionsTab can={can} />}
      {tab === "roles" && <RolesTab can={can} />}
      {tab === "teams" && <TeamsTab can={can} />}
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// 员工 Tab
// ──────────────────────────────────────────────────────────────

function StaffTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = useEmployees({ type: "human" });
  const [selected, setSelected] = useState<EmployeeRow | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);

  const employeeRemove = can("employee_remove");
  const employeeInvite = can("employee_invite");

  if (loading && items.length === 0) {
    return <ConsolePageState kind="loading" />;
  }
  if (error) {
    return <ConsolePageState kind="error" description={error} />;
  }

  return (
    <>
      <ConsoleSection
        title={`员工（${items.length}）`}
        actions={
          <span className="flex items-center gap-2">
            {employeeInvite && (
              <button
                type="button"
                className="hud-btn text-xs"
                onClick={() => setInviteOpen(true)}
              >
                邀请
              </button>
            )}
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
              onClick={refresh}
            >
              刷新
            </button>
          </span>
        }
      >
        <ConsoleTable<EmployeeRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无员工"
          onRowClick={(row) => setSelected(row)}
          columns={[
            {
              key: "id",
              header: "ID",
              render: (row) => <span className="font-mono">{row.id.slice(0, 8)}</span>,
            },
            { key: "displayName", header: "姓名", render: (row) => row.displayName },
            {
              key: "status",
              header: "状态",
              render: (row) => {
                const label = EMPLOYEE_STATUS_LABELS[row.status] ?? row.status;
                const tone: "ok" | "warn" | "danger" | "default" =
                  row.status === "active"
                    ? "ok"
                    : row.status === "pending"
                      ? "warn"
                      : row.status === "disabled"
                        ? "danger"
                        : "default";
                return <ConsoleTag tone={tone}>{label}</ConsoleTag>;
              },
            },
            {
              key: "accountType",
              header: "类型",
              render: (row) => (
                <ConsoleTag>{ACCOUNT_TYPE_LABELS[row.accountType] ?? row.accountType}</ConsoleTag>
              ),
            },
            {
              key: "dataScope",
              header: "数据范围",
              render: (row) => (
                <ConsoleTag>{DATA_SCOPE_LABEL[row.dataScope as keyof typeof DATA_SCOPE_LABEL] ?? row.dataScope}</ConsoleTag>
              ),
            },
            {
              key: "online",
              header: "在线",
              render: (row) =>
                row.online ? (
                  <ConsoleTag tone="ok">在线</ConsoleTag>
                ) : (
                  <ConsoleTag tone="default">离线</ConsoleTag>
                ),
            },
            {
              key: "actions",
              header: "操作",
              render: (row) => (
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelected(row);
                    }}
                  >
                    详情
                  </button>
                  {employeeRemove && (
                    <RemoveEmployeeButton
                      employee={row}
                      onRemoved={() => {
                        setSelected(null);
                        refresh();
                      }}
                    />
                  )}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {selected && (
        <EmployeeDrawer
          employee={selected}
          can={can}
          onClose={() => setSelected(null)}
          onSaved={(updated) => {
            setSelected(updated);
            refresh();
          }}
        />
      )}

      {inviteOpen && (
        <InviteEmployeeDialog
          onClose={() => setInviteOpen(false)}
          onDone={() => {
            setInviteOpen(false);
            refresh();
          }}
        />
      )}
    </>
  );
}

// ── 员工详情抽屉 ────────────────────────────────────────────────

type EmployeeDrawerTab = "profile" | "roles-skills" | "permissions" | "seat-contact";
const EMPLOYEE_DRAWER_TABS: { key: EmployeeDrawerTab; label: string }[] = [
  { key: "profile", label: "档案" },
  { key: "roles-skills", label: "角色与技能" },
  { key: "permissions", label: "权限" },
  { key: "seat-contact", label: "工位与联系人" },
];

function EmployeeDrawer({
  employee,
  can,
  onClose,
  onSaved,
}: {
  employee: EmployeeRow;
  can: (c: string) => boolean;
  onClose: () => void;
  onSaved: (updated: EmployeeRow) => void;
}) {
  const [tab, setTab] = useState<EmployeeDrawerTab>("profile");

  // 档案子 Tab 的可编辑字段
  const [form, setForm] = useState({
    display_name: employee.displayName,
    data_scope: employee.dataScope,
    enabled: employee.status !== "removed" && employee.status !== "disabled",
  });
  const [saving, setSaving] = useState(false);
  const [conflictMsg, setConflictMsg] = useState<string | null>(null);

  // 角色/权限/技能
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const [caps, setCaps] = useState<string[]>([]);
  const [perms, setPerms] = useState<string[]>(employee.permissions);
  const [rolesLoading, setRolesLoading] = useState(true);
  const [capsLoading, setCapsLoading] = useState(true);
  const [rolesError, setRolesError] = useState<string | null>(null);

  // 可选引用数据
  const { items: positionOptions } = usePositions({ limit: 200 });
  const { items: teamOptions } = useTeams({ limit: 200 });

  const consoleAdmin = can("console_admin");

  useEffect(() => {
    setForm({
      display_name: employee.displayName,
      data_scope: employee.dataScope,
      enabled: employee.status !== "removed" && employee.status !== "disabled",
    });
    setPerms(employee.permissions);
  }, [employee]);

  useEffect(() => {
    let disposed = false;
    setRolesLoading(true);
    Promise.all([
      getEmployeeRoles(employee.id),
      getEmployeeCapabilities(employee.id),
      consoleAdmin ? getEmployeePermissions(employee.id) : Promise.resolve({ ok: true, data: { permissions: employee.permissions } }),
    ]).then(([rolesRes, capsRes, permsRes]) => {
      if (disposed) return;
      setRolesLoading(false);
      setCapsLoading(false);
      if (rolesRes.ok && rolesRes.data) setRoleIds(rolesRes.data.role_ids);
      if (capsRes.ok && capsRes.data) setCaps(capsRes.data.capabilities);
      if (permsRes.ok && permsRes.data) setPerms(permsRes.data.permissions);
      if (!rolesRes.ok || !capsRes.ok) {
        const errMsg = !rolesRes.ok ? rolesRes.error : (!capsRes.ok ? capsRes.error : null);
        setRolesError(errMsg || "加载失败");
      }
    });
    return () => {
      disposed = true;
    };
  }, [employee.id, consoleAdmin]);

  const handleSaveProfile = useCallback(async () => {
    setSaving(true);
    setConflictMsg(null);
    const res = await updateEmployee(employee.id, {
      display_name: form.display_name,
      data_scope: form.data_scope as any,
      enabled: form.enabled,
    });
    setSaving(false);
    if (res.ok && res.data) {
      onSaved(mapEmployee(res.data));
    } else if (!res.ok) {
      if (res.status === 409) {
        setConflictMsg(res.error || "数据冲突，请稍后重试");
      } else {
        setConflictMsg(res.error || "保存失败");
      }
    }
  }, [employee.id, form, onSaved]);

  const handleSaveRolesSkills = useCallback(async () => {
    setSaving(true);
    const rolesRes = await putEmployeeRoles(employee.id, { role_ids: roleIds });
    const capsRes = await putEmployeeCapabilities(employee.id, { capabilities: caps });
    setSaving(false);
    if (rolesRes.ok && capsRes.ok) {
      onSaved(employee); // 刷新即可
    }
  }, [employee.id, roleIds, caps, employee, onSaved]);

  const handleSavePermissions = useCallback(async () => {
    setSaving(true);
    const res = await putEmployeePermissions(employee.id, { permissions: perms });
    setSaving(false);
    if (res.ok && res.data) {
      onSaved({ ...employee, permissions: res.data.permissions });
    }
  }, [employee.id, perms, employee, onSaved]);

  const hasChanges =
    form.display_name !== employee.displayName ||
    form.data_scope !== employee.dataScope ||
    (form.enabled && (employee.status === "removed" || employee.status === "disabled")) ||
    (!form.enabled && employee.status === "active");

  return (
    <ConsoleDrawer
      open
      onClose={onClose}
      width={640}
      title={`员工 — ${employee.displayName}`}
      description={employee.id}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
            onClick={onClose}
          >
            取消
          </button>
          {tab === "profile" && (
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={saving || !hasChanges}
              onClick={() => void handleSaveProfile()}
            >
              {saving ? "保存中…" : "保存"}
            </button>
          )}
          {(tab === "roles-skills" || tab === "permissions") && (
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={saving}
              onClick={() => {
                if (tab === "roles-skills") void handleSaveRolesSkills();
                else void handleSavePermissions();
              }}
            >
              {saving ? "保存中…" : "保存"}
            </button>
          )}
        </div>
      }
    >
      <ConsoleTabs
        tabs={EMPLOYEE_DRAWER_TABS}
        value={tab}
        onChange={setTab}
      />
      {tab === "profile" && (
        <div className="space-y-4">
          <p className="text-xs text-mute">可编辑字段：display_name / data_scope / enabled；只读字段不显示输入框。</p>
          <EditField label="姓名">
            <input
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={form.display_name}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
            />
          </EditField>
          <EditField label="数据范围">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={form.data_scope}
              onChange={(e) => setForm((f) => ({ ...f, data_scope: e.target.value }))}
            >
              <option value="self">仅本人</option>
              <option value="team">本团队</option>
              <option value="global">全部</option>
            </select>
          </EditField>
          <EditField label="启用">
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              {form.enabled ? "启用中" : "已停用"}
            </label>
          </EditField>
          <hr className="border-rail" />
          <ReadOnlyField label="状态">
            <ConsoleTag tone={
              employee.status === "active" ? "ok" :
              employee.status === "pending" ? "warn" :
              employee.status === "disabled" ? "danger" : "default"
            }>
              {EMPLOYEE_STATUS_LABELS[employee.status] ?? employee.status}
            </ConsoleTag>
          </ReadOnlyField>
          <ReadOnlyField label="端点审批">
            <ConsoleTag tone={employee.endpointApproved ? "ok" : "warn"}>
              {employee.endpointApproved ? "已批准" : "待审批"}
            </ConsoleTag>
          </ReadOnlyField>
          <ReadOnlyField label="类型">
            <ConsoleTag>{ACCOUNT_TYPE_LABELS[employee.accountType] ?? employee.accountType}</ConsoleTag>
          </ReadOnlyField>
          {employee.lastHeartbeat && (
            <ReadOnlyField label="最后心跳">
              <span className="font-mono text-xs">{employee.lastHeartbeat}</span>
            </ReadOnlyField>
          )}
          {employee.accountType === "agent" && (
            <>
              <hr className="border-rail" />
              <p className="text-xs font-medium text-mint">Agent 绑定</p>
              <ReadOnlyField label="Agent ID">
                <span className="font-mono text-xs">{employee.agentId ?? "—"}</span>
              </ReadOnlyField>
              <ReadOnlyField label="Agent 名称">
                <span className="text-xs">{employee.agentName ?? "—"}</span>
              </ReadOnlyField>
              <ReadOnlyField label="框架">
                <span className="text-xs">{employee.agentFramework ?? "—"}</span>
              </ReadOnlyField>
            </>
          )}
          {conflictMsg && (
            <p className="text-xs text-flare">{conflictMsg}（输入已保留，请稍后重试）</p>
          )}
        </div>
      )}

      {tab === "roles-skills" && (
        <div className="space-y-4">
          {rolesLoading || capsLoading ? (
            <ConsolePageState kind="loading" />
          ) : rolesError ? (
            <ConsolePageState kind="error" description={rolesError} />
          ) : (
            <>
              <div>
                <p className="mb-2 text-xs font-medium text-frost/90">角色</p>
                <div className="space-y-1">
                  <RolePicker roleIds={roleIds} onChange={setRoleIds} />
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-frost/90">能力（capabilities）</p>
                <div className="flex flex-wrap gap-2">
                  {caps.length === 0 && <span className="text-xs text-mute">暂无能力</span>}
                  {caps.map((cap) => (
                    <ConsoleTag key={cap}>{cap}</ConsoleTag>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-mute">能力由岗位/角色聚合，如需调整请编辑对应岗位或角色。</p>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "permissions" && (
        <div className="space-y-4">
          {!consoleAdmin ? (
            <ConsolePageState
              kind="forbidden"
              title="仅 console_admin 可修改权限"
              description="当前标签页只读展示。"
            />
          ) : (
            <>
              <p className="text-xs text-mute">21 个权限分组展示，勾选后保存。</p>
              {PERMISSION_GROUPS.map((group) => (
                <div key={group.key}>
                  <p className="mb-2 text-xs font-medium text-frost/90">{group.label}</p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {group.permissions.map((p) => {
                      const checked = perms.includes(p.key);
                      return (
                        <label
                          key={p.key}
                          className="flex items-center gap-1.5 text-xs"
                          title={p.description}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setPerms((prev) => [...prev, p.key]);
                              } else {
                                setPerms((prev) => prev.filter((x) => x !== p.key));
                              }
                            }}
                          />
                          <span>{PERMISSION_LABELS[p.key]}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {tab === "seat-contact" && (
        <div className="space-y-4">
          <p className="text-xs text-mute">工位 / 岗位 / 团队关联。</p>
          <EditField label="团队">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={employee.teamId ?? ""}
              onChange={async (e) => {
                const v = e.target.value || null;
                const res = await updateEmployee(employee.id, { team_id: v });
                if (res.ok && res.data) onSaved(mapEmployee(res.data));
              }}
            >
              <option value="">（未分配）</option>
              {teamOptions.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </EditField>
          <EditField label="岗位">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={employee.positionId ?? ""}
              onChange={async (e) => {
                const v = e.target.value || null;
                const res = await updateEmployee(employee.id, { position_id: v });
                if (res.ok && res.data) onSaved(mapEmployee(res.data));
              }}
            >
              <option value="">（未分配）</option>
              {positionOptions.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </EditField>
          <hr className="border-rail" />
          <div>
            <p className="mb-1 text-xs font-medium text-frost/90">联系人</p>
            <ConsolePageState
              kind="empty"
              title="联系人增删契约未冻结"
              description="后端暂未开放联系人 REST 端点，待 B1.5 契约补齐后接入。"
            />
          </div>
        </div>
      )}
    </ConsoleDrawer>
  );
}

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-mute">{label}</span>
      {children}
    </label>
  );
}

function ReadOnlyField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 shrink-0 text-mute">{label}</span>
      <span>{children}</span>
    </div>
  );
}

// ── 邀请真人对话框 ─────────────────────────────────────────────

function InviteEmployeeDialog({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [dataScope, setDataScope] = useState<"self" | "team" | "global">("self");
  const [expiresIn, setExpiresIn] = useState<number>(24);
  const [positionId, setPositionId] = useState<string>("");
  const [teamId, setTeamId] = useState<string>("");
  const [perms, setPerms] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [oneTimeCode, setOneTimeCode] = useState<string | null>(null);

  const { items: positionOptions } = usePositions({ limit: 200 });
  const { items: teamOptions } = useTeams({ limit: 200 });

  const submit = async () => {
    if (!displayName.trim()) {
      setErr("姓名不能为空");
      return;
    }
    setErr(null);
    setBusy(true);
    const res = await inviteEmployee({
      display_name: displayName.trim(),
      data_scope: dataScope,
      expires_in_hours: expiresIn,
      position_id: positionId || null,
      team_id: teamId || null,
      permissions: perms,
    });
    setBusy(false);
    if (res.ok && res.data) {
      setOneTimeCode(res.data.invite_code ?? null);
    } else if (!res.ok) {
      setErr(res.error || "邀请失败");
    }
  };

  // 邀请码明文仅组件内持有；关闭即清空
  const finish = () => {
    setOneTimeCode(null);
    onDone();
  };

  return (
    <ConsoleDrawer
      open
      onClose={onClose}
      width={640}
      title="邀请真人员工"
      description={oneTimeCode ? "邀请码仅本次显示" : "填写后生成一次性邀请码"}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
            onClick={oneTimeCode ? finish : onClose}
          >
            {oneTimeCode ? "完成" : "取消"}
          </button>
          {!oneTimeCode && (
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={busy}
              onClick={() => void submit()}
            >
              {busy ? "提交中…" : "生成邀请码"}
            </button>
          )}
        </div>
      }
    >
      {oneTimeCode ? (
        <div className="space-y-3">
          <p className="text-xs text-mute">邀请码仅本次展示，关闭后不再可见。</p>
          <div className="rounded border border-mint/40 bg-mint/5 px-3 py-2 font-mono text-sm text-mint break-all">
            {oneTimeCode}
          </div>
          <p className="text-[11px] text-mute">
            被邀请人使用此码通过 /join 或 /invite/accept 完成注册。
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <EditField label="姓名 *">
            <input
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </EditField>
          <EditField label="数据范围">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={dataScope}
              onChange={(e) => setDataScope(e.target.value as any)}
            >
              <option value="self">仅本人</option>
              <option value="team">本团队</option>
              <option value="global">全部</option>
            </select>
          </EditField>
          <EditField label="有效期（小时）">
            <input
              type="number"
              min={1}
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={expiresIn}
              onChange={(e) => setExpiresIn(Number(e.target.value) || 24)}
            />
          </EditField>
          <EditField label="岗位（可选）">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={positionId}
              onChange={(e) => setPositionId(e.target.value)}
            >
              <option value="">（不指定）</option>
              {positionOptions.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </EditField>
          <EditField label="团队（可选）">
            <select
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
            >
              <option value="">（不指定）</option>
              {teamOptions.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </EditField>
          <div>
            <p className="mb-1 text-[11px] text-mute">初始权限</p>
            <div className="grid grid-cols-2 gap-1.5">
              {ALL_PERMISSIONS.map((p) => {
                const checked = perms.includes(p);
                return (
                  <label key={p} className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setPerms((prev) => [...prev, p]);
                        else setPerms((prev) => prev.filter((x) => x !== p));
                      }}
                    />
                    <span>{PERMISSION_LABELS[p]}</span>
                  </label>
                );
              })}
            </div>
          </div>
          {err && <p className="text-xs text-flare">{err}</p>}
        </div>
      )}
    </ConsoleDrawer>
  );
}

// ── 角色 Picker（供抽屉内使用）─────────────────────────────────

function RolePicker({
  roleIds,
  onChange,
}: {
  roleIds: string[];
  onChange: (next: string[]) => void;
}) {
  const { items } = useRoles({ limit: 200 });
  if (items.length === 0) {
    return <p className="text-xs text-mute">暂无可选角色</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((r) => {
        const checked = roleIds.includes(r.id);
        return (
          <label
            key={r.id}
            className={`flex items-center gap-1 rounded border px-2 py-1 text-xs ${
              checked ? "border-mint/60 text-mint" : "border-rail text-mute"
            }`}
          >
            <input
              type="checkbox"
              className="accent-mint"
              checked={checked}
              onChange={(e) => {
                if (e.target.checked) onChange([...roleIds, r.id]);
                else onChange(roleIds.filter((x) => x !== r.id));
              }}
            />
            {r.name}
          </label>
        );
      })}
    </div>
  );
}

// ── 移除员工按钮 ───────────────────────────────────────────────

function RemoveEmployeeButton({
  employee,
  onRemoved,
}: {
  employee: EmployeeRow;
  onRemoved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setErr(null);
    const res = await deleteEmployee(employee.id);
    setBusy(false);
    if (res.ok) {
      setOpen(false);
      onRemoved();
    } else if (!res.ok) {
      setErr(res.error || "移除失败");
    }
  };

  return (
    <>
      <button
        type="button"
        className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        移除
      </button>
      <ConfirmDialog
        open={open}
        title={`移除员工「${employee.displayName}」？`}
        description={err ?? "软移除：状态标记为 removed，可审计追溯。"}
        danger
        busy={busy}
        confirmLabel="移除"
        onConfirm={() => void confirm()}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// 岗位 Tab（左右双栏）
// ──────────────────────────────────────────────────────────────

function PositionsTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = usePositions({ limit: 200 });
  const [selected, setSelected] = useState<PositionRow | null>(null);
  const [form, setForm] = useState({ name: "", capabilities: [] as string[] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canManage = can("role_manage") || can("org_manage");

  const startEdit = (p: PositionRow | null) => {
    setSelected(p);
    setForm({ name: p?.name ?? "", capabilities: p?.capabilities ?? [] });
    setErr(null);
  };

  const save = async () => {
    if (!form.name.trim()) {
      setErr("岗位名称不能为空");
      return;
    }
    setBusy(true);
    setErr(null);
    const body: any = { name: form.name.trim(), capabilities: form.capabilities };
    const res = selected
      ? await updatePosition(selected.id, body)
      : await createPosition(body);
    setBusy(false);
    if (res.ok && res.data) {
      startEdit(mapPositionOnly(res.data));
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "保存失败");
    }
  };

  const remove = async () => {
    if (!selected) return;
    setBusy(true);
    setErr(null);
    const res = await deletePosition(selected.id);
    setBusy(false);
    if (res.ok) {
      startEdit(null);
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "删除失败");
    }
  };

  if (loading && items.length === 0) return <ConsolePageState kind="loading" />;
  if (error) return <ConsolePageState kind="error" description={error} />;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1fr]">
      <ConsoleSection
        title={`岗位（${items.length}）`}
        actions={
          canManage ? (
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => startEdit(null)}
            >
              新建
            </button>
          ) : null
        }
      >
        <ConsoleTable<PositionRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无岗位"
          onRowClick={(row) => startEdit(row)}
          selectedKey={selected?.id}
          columns={[
            { key: "name", header: "名称", render: (row) => row.name },
            {
              key: "caps",
              header: "能力",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  {row.capabilities.length
                    ? row.capabilities.map((c) => <ConsoleTag key={c}>{c}</ConsoleTag>)
                    : "—"}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title={selected ? `编辑：${selected.name}` : "新建岗位"}>
        <div className="space-y-3">
          <EditField label="名称">
            <input
              className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              value={form.name}
              disabled={!canManage}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </EditField>
          <EditField label="能力（capabilities）">
            <CapabilityPicker
              values={form.capabilities}
              disabled={!canManage}
              onChange={(caps) => setForm((f) => ({ ...f, capabilities: caps }))}
            />
          </EditField>
          {err && <p className="text-xs text-flare">{err}</p>}
          {canManage && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={busy}
                onClick={() => void save()}
              >
                {busy ? "保存中…" : selected ? "保存修改" : "创建"}
              </button>
              {selected && (
                <>
                  <button
                    type="button"
                    className="rounded border border-flare/50 px-3 py-1.5 text-xs text-flare hover:bg-flare/10 disabled:opacity-40"
                    disabled={busy}
                    onClick={() => void remove()}
                  >
                    删除
                  </button>
                  <button
                    type="button"
                    className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                    onClick={() => startEdit(null)}
                  >
                    取消
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </ConsoleSection>
    </div>
  );
}

// 复用的 capability picker（手动添加 tag）
function CapabilityPicker({
  values,
  onChange,
  disabled,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (!v || values.includes(v)) return;
    onChange([...values, v]);
    setInput("");
  };
  return (
    <div>
      <div className="mb-1 flex flex-wrap gap-1">
        {values.length === 0 && <span className="text-xs text-mute">（无）</span>}
        {values.map((c) => (
          <span
            key={c}
            className="inline-flex items-center gap-1 rounded border border-rail px-1.5 py-0.5 text-[11px]"
          >
            {c}
            {!disabled && (
              <button
                type="button"
                aria-label={`移除 ${c}`}
                className="text-mute hover:text-flare"
                onClick={() => onChange(values.filter((x) => x !== c))}
              >
                ✕
              </button>
            )}
          </span>
        ))}
      </div>
      {!disabled && (
        <div className="flex gap-2">
          <input
            className="min-w-0 flex-1 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="输入 capability 后回车"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <button
            type="button"
            className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-frost"
            onClick={add}
          >
            添加
          </button>
        </div>
      )}
    </div>
  );
}

function mapPositionOnly(p: { position_id: string; name: string; capabilities?: string[]; role_ids?: string[] }): PositionRow {
  return { id: p.position_id, name: p.name, capabilities: p.capabilities ?? [], roleIds: p.role_ids ?? [] };
}

// ──────────────────────────────────────────────────────────────
// 角色 Tab
// ──────────────────────────────────────────────────────────────

function RolesTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = useRoles({ limit: 200 });
  const [selected, setSelected] = useState<RoleRow | null>(null);
  const [form, setForm] = useState({
    name: "",
    enabled: true,
    description: "",
    capabilities: [] as string[],
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canManage = can("role_manage") || can("org_manage");

  const openDrawer = (r: RoleRow | null) => {
    setSelected(r);
    setForm({
      name: r?.name ?? "",
      enabled: r?.enabled ?? true,
      description: r?.description ?? "",
      capabilities: r?.capabilities ?? [],
    });
    setErr(null);
  };

  const save = async () => {
    if (!form.name.trim()) {
      setErr("角色名称不能为空");
      return;
    }
    setBusy(true);
    setErr(null);
    const body: any = {
      name: form.name.trim(),
      enabled: form.enabled,
      description: form.description.trim() || null,
      capabilities: form.capabilities,
    };
    const res = selected
      ? await updateRole(selected.id, body)
      : await createRole(body);
    setBusy(false);
    if (res.ok && res.data) {
      setSelected(null);
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "保存失败");
    }
  };

  const remove = async () => {
    if (!selected) return;
    setBusy(true);
    setErr(null);
    const res = await deleteRole(selected.id);
    setBusy(false);
    if (res.ok) {
      setSelected(null);
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "删除失败");
    }
  };

  if (loading && items.length === 0) return <ConsolePageState kind="loading" />;
  if (error) return <ConsolePageState kind="error" description={error} />;

  return (
    <>
      <ConsoleSection
        title={`角色（${items.length}）`}
        actions={
          canManage ? (
            <button type="button" className="hud-btn text-xs" onClick={() => openDrawer(null)}>
              新建
            </button>
          ) : null
        }
      >
        <ConsoleTable<RoleRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无角色"
          onRowClick={(row) => openDrawer(row)}
          columns={[
            { key: "name", header: "名称", render: (row) => row.name },
            {
              key: "enabled",
              header: "状态",
              render: (row) =>
                row.enabled ? (
                  <ConsoleTag tone="ok">启用</ConsoleTag>
                ) : (
                  <ConsoleTag tone="danger">停用</ConsoleTag>
                ),
            },
            { key: "desc", header: "描述", render: (row) => row.description ?? "—" },
            {
              key: "caps",
              header: "能力",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  {row.capabilities.length
                    ? row.capabilities.slice(0, 3).map((c) => <ConsoleTag key={c}>{c}</ConsoleTag>)
                    : "—"}
                  {row.capabilities.length > 3 && (
                    <span className="text-[11px] text-mute">+{row.capabilities.length - 3}</span>
                  )}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {selected !== null && (
        <ConsoleDrawer
          open
          width={640}
          onClose={() => openDrawer(null)}
          title={selected ? `编辑角色 — ${selected.name}` : "新建角色"}
          footer={
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                onClick={() => openDrawer(null)}
              >
                取消
              </button>
              {canManage && selected && (
                <button
                  type="button"
                  className="rounded border border-flare/50 px-3 py-1.5 text-xs text-flare hover:bg-flare/10 disabled:opacity-40"
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  删除
                </button>
              )}
              {canManage && (
                <button
                  type="button"
                  className="hud-btn text-xs disabled:opacity-40"
                  disabled={busy}
                  onClick={() => void save()}
                >
                  {busy ? "保存中…" : selected ? "保存修改" : "创建"}
                </button>
              )}
            </div>
          }
        >
          <div className="space-y-3">
            <EditField label="名称">
              <input
                className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
                value={form.name}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </EditField>
            <EditField label="启用">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  disabled={!canManage}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
                {form.enabled ? "启用中" : "已停用"}
              </label>
            </EditField>
            <EditField label="描述">
              <textarea
                rows={2}
                className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
                value={form.description}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </EditField>
            <EditField label="能力">
              <CapabilityPicker
                values={form.capabilities}
                disabled={!canManage}
                onChange={(caps) => setForm((f) => ({ ...f, capabilities: caps }))}
              />
            </EditField>
            {err && <p className="text-xs text-flare">{err}</p>}
          </div>
        </ConsoleDrawer>
      )}
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// 团队 Tab
// ──────────────────────────────────────────────────────────────

type SeatView = {
  seat_id: string;
  employee_id?: string | null;
  position_id?: string | null;
  team_id?: string | null;
  x?: number | null;
  y?: number | null;
};

function TeamsTab({ can }: { can: (c: string) => boolean }) {
  const { items, loading, error, refresh } = useTeams({ limit: 200 });
  const [selected, setSelected] = useState<TeamRow | null>(null);
  const [seats, setSeats] = useState<SeatView[]>([]);
  const [seatsLoading, setSeatsLoading] = useState(false);
  const [form, setForm] = useState({ name: "", leader_employee_id: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canManage = can("org_manage");
  const { items: positionOptions } = usePositions({ limit: 200 });
  const { items: employeeOptions } = useEmployees({ type: "human", limit: 200 });

  const refreshSeats = async (teamId: string) => {
    setSeatsLoading(true);
    const res = await listTeamSeats(teamId);
    setSeatsLoading(false);
    if (res.ok && res.data) {
      setSeats(res.data.items as SeatView[]);
    } else {
      setSeats([]);
    }
  };

  useEffect(() => {
    if (selected) void refreshSeats(selected.id);
    else setSeats([]);
  }, [selected?.id]);

  const createNew = () => {
    setSelected(null);
    setForm({ name: "", leader_employee_id: "" });
    setErr(null);
  };

  const save = async () => {
    if (!form.name.trim()) {
      setErr("团队名称不能为空");
      return;
    }
    setBusy(true);
    setErr(null);
    const body: any = {
      name: form.name.trim(),
      leader_employee_id: form.leader_employee_id || null,
    };
    const res = selected
      ? await updateTeam(selected.id, body)
      : await createTeam(body);
    setBusy(false);
    if (res.ok && res.data) {
      setSelected(null);
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "保存失败");
    }
  };

  const remove = async () => {
    if (!selected) return;
    setBusy(true);
    setErr(null);
    const res = await deleteTeam(selected.id);
    setBusy(false);
    if (res.ok) {
      setSelected(null);
      refresh();
    } else if (!res.ok) {
      setErr(res.error || "删除失败");
    }
  };

  const assignEmployeeToSeat = async (seat: SeatView, employeeId: string) => {
    const res = await assignSeat(seat.seat_id, {
      employee_id: employeeId || null,
      position_id: seat.position_id ?? null,
      team_id: seat.team_id ?? null,
    });
    if (res.ok) void refreshSeats(seat.team_id ?? selected!.id);
  };

  const assignPositionToSeat = async (seat: SeatView, positionId: string) => {
    const res = await assignSeat(seat.seat_id, {
      employee_id: seat.employee_id ?? null,
      position_id: positionId || null,
      team_id: seat.team_id ?? null,
    });
    if (res.ok) void refreshSeats(seat.team_id ?? selected!.id);
  };

  if (loading && items.length === 0) return <ConsolePageState kind="loading" />;
  if (error) return <ConsolePageState kind="error" description={error} />;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1fr]">
      <ConsoleSection
        title={`团队（${items.length}）`}
        actions={
          canManage ? (
            <button type="button" className="hud-btn text-xs" onClick={createNew}>
              新建
            </button>
          ) : null
        }
      >
        <ConsoleTable<TeamRow>
          rows={items}
          rowKey={(row) => row.id}
          loading={loading}
          empty="暂无团队"
          onRowClick={(row) => {
            setSelected(row);
            setForm({ name: row.name, leader_employee_id: row.leaderEmployeeId ?? "" });
            setErr(null);
          }}
          selectedKey={selected?.id}
          columns={[
            { key: "name", header: "名称", render: (row) => row.name },
            {
              key: "leader",
              header: "负责人",
              render: (row) => row.leaderEmployeeId ? (
                <span className="font-mono text-[11px]">{row.leaderEmployeeId.slice(0, 8)}</span>
              ) : "—",
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title={selected ? `工位网格 — ${selected.name}` : "团队详情"}>
        {!selected ? (
          <p className="text-xs text-mute">选择左侧团队以查看工位。</p>
        ) : seatsLoading ? (
          <ConsolePageState kind="loading" />
        ) : seats.length === 0 ? (
          <ConsolePageState kind="empty" title="暂无工位" />
        ) : (
          <div className="space-y-2">
            {seats.map((seat) => {
              const emp = employeeOptions.find((e: EmployeeRow) => e.id === seat.employee_id);
              const pos = positionOptions.find((p: PositionRow) => p.id === seat.position_id);
              return (
                <div
                  key={seat.seat_id}
                  className="flex flex-wrap items-center gap-2 rounded border border-rail px-3 py-2 text-xs"
                >
                  <span className="font-mono text-mute">{seat.seat_id.slice(0, 8)}</span>
                  {seat.x !== null && seat.x !== undefined && seat.y !== null && seat.y !== undefined && (
                    <span className="font-mono text-mute text-[10px]">
                      ({seat.x},{seat.y})
                    </span>
                  )}
                  {canManage ? (
                    <>
                      <select
                        className="rounded border border-rail bg-hull px-1 py-0.5 text-xs"
                        value={seat.position_id ?? ""}
                        onChange={(e) => void assignPositionToSeat(seat, e.target.value)}
                      >
                        <option value="">（无岗位）</option>
                        {positionOptions.map((p: PositionRow) => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                      <select
                        className="rounded border border-rail bg-hull px-1 py-0.5 text-xs"
                        value={seat.employee_id ?? ""}
                        onChange={(e) => void assignEmployeeToSeat(seat, e.target.value)}
                      >
                        <option value="">（未分配）</option>
                        {employeeOptions.map((e: EmployeeRow) => (
                          <option key={e.id} value={e.id}>{e.displayName}</option>
                        ))}
                      </select>
                    </>
                  ) : (
                    <>
                      <ConsoleTag>{pos?.name ?? "—"}</ConsoleTag>
                      <span>{emp?.displayName ?? "空位"}</span>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </ConsoleSection>

      {canManage && (
        <ConsoleSection title={selected ? "编辑团队" : "新建团队"}>
          <div className="space-y-3">
            <EditField label="名称">
              <input
                className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </EditField>
            <EditField label="负责人（可选）">
              <select
                className="w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                value={form.leader_employee_id}
                onChange={(e) => setForm((f) => ({ ...f, leader_employee_id: e.target.value }))}
              >
                <option value="">（不指定）</option>
                {employeeOptions.map((e: EmployeeRow) => (
                  <option key={e.id} value={e.id}>{e.displayName}</option>
                ))}
              </select>
            </EditField>
            {err && <p className="text-xs text-flare">{err}</p>}
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={busy}
                onClick={() => void save()}
              >
                {busy ? "保存中…" : selected ? "保存修改" : "创建"}
              </button>
              {selected && (
                <>
                  <button
                    type="button"
                    className="rounded border border-flare/50 px-3 py-1.5 text-xs text-flare hover:bg-flare/10 disabled:opacity-40"
                    disabled={busy}
                    onClick={() => void remove()}
                  >
                    删除
                  </button>
                  <button
                    type="button"
                    className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                    onClick={createNew}
                  >
                    取消
                  </button>
                </>
              )}
            </div>
          </div>
        </ConsoleSection>
      )}
    </div>
  );
}
