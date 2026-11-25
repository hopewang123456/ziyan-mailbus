import type { components } from "../contracts";
import type { DataScope } from "../permissions";

/**
 * 组织域视图模型：只做展示映射，不新增服务端字段。
 * 组件只消费 view.ts 导出的类型，不直接依赖 contracts。
 */

export type EmployeeRow = {
  id: string;
  accountType: string;
  displayName: string;
  status: string;
  dataScope: string;
  endpointApproved: boolean;
  positionId?: string | null;
  seatId?: string | null;
  teamId?: string | null;
  agentId?: string | null;
  agentName?: string | null;
  agentFramework?: string | null;
  lastHeartbeat?: string | null;
  online: boolean;
  permissions: string[];
};

export type PositionRow = {
  id: string;
  name: string;
  capabilities: string[];
  roleIds: string[];
  createdAt?: string | null;
};

export type RoleRow = {
  id: string;
  name: string;
  enabled: boolean;
  capabilities: string[];
  color?: string | null;
  description?: string | null;
  icon?: string | null;
};

export type TeamRow = {
  id: string;
  name: string;
  leaderEmployeeId?: string | null;
};

export type InviteRow = {
  id: string;
  displayName: string;
  dataScope: string;
  permissions: string[];
  positionId?: string | null;
  teamId?: string | null;
  expiresAt?: string | null;
  revokedAt?: string | null;
  consumedAt?: string | null;
  // 明文仅创建/重发响应返回一次
  oneTimeCode?: string | null;
};

export function mapEmployee(e: components["schemas"]["EmployeeOut"]): EmployeeRow {
  const heartbeat = e.last_heartbeat ?? null;
  const online = heartbeat ? isRecentlyActive(heartbeat, 120) : false;
  return {
    id: e.employee_id,
    accountType: e.account_type,
    displayName: e.display_name,
    status: e.status,
    dataScope: e.data_scope,
    endpointApproved: e.endpoint_approved,
    positionId: e.position_id,
    seatId: e.seat_id,
    teamId: e.team_id,
    agentId: e.agent_id,
    agentName: e.agent_name,
    agentFramework: e.agent_framework,
    lastHeartbeat: heartbeat,
    online,
    permissions: e.permissions ?? [],
  };
}

export function mapPosition(p: components["schemas"]["PositionOut"]): PositionRow {
  return {
    id: p.position_id,
    name: p.name,
    capabilities: p.capabilities ?? [],
    roleIds: p.role_ids ?? [],
    createdAt: p.created_at,
  };
}

export function mapRole(r: components["schemas"]["RoleOut"]): RoleRow {
  return {
    id: r.role_id,
    name: r.name,
    enabled: r.enabled,
    capabilities: r.capabilities ?? [],
    color: r.color,
    description: r.description,
    icon: r.icon,
  };
}

export function mapTeam(t: components["schemas"]["mailbus__api__schemas__contract__org__TeamOut"]): TeamRow {
  return {
    id: t.team_id,
    name: t.name,
    leaderEmployeeId: t.leader_employee_id,
  };
}

export function mapInvite(i: components["schemas"]["InviteOut"]): InviteRow {
  return {
    id: i.invite_id,
    displayName: "(未命名)",
    dataScope: i.data_scope,
    permissions: i.permissions ?? [],
    positionId: i.position_id,
    teamId: i.team_id,
    expiresAt: i.expires_at,
    revokedAt: i.revoked_at,
    consumedAt: i.consumed_at,
    oneTimeCode: i.invite_code ?? null,
  };
}

/** 判断 ISO UTC 时间是否在 N 秒内活跃过。 */
export function isRecentlyActive(iso: string, windowSeconds: number): boolean {
  try {
    const t = new Date(iso).getTime();
    return Date.now() - t < windowSeconds * 1000;
  } catch {
    return false;
  }
}

export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  human: "真人",
  agent: "Agent",
};

export const EMPLOYEE_STATUS_LABELS: Record<string, string> = {
  active: "在职",
  pending: "待审核",
  disabled: "已停用",
  removed: "已移除",
};

export const DATA_SCOPE_LABEL: Record<DataScope, string> = {
  self: "仅本人",
  team: "本团队",
  global: "全部",
};
