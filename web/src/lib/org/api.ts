import { api } from "../api";
import type { components } from "../contracts";

/**
 * 组织域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type EmployeeListOut = components["schemas"]["EmployeeListOut"];
type EmployeeOut = components["schemas"]["EmployeeOut"];
type EmployeeUpdateIn = components["schemas"]["EmployeeUpdateIn"];
type EmployeeInviteIn = components["schemas"]["EmployeeInviteIn"];
type InviteOut = components["schemas"]["InviteOut"];
type PosListOut = components["schemas"]["PositionListOut"];
type PositionOut = components["schemas"]["PositionOut"];
type PositionIn = components["schemas"]["PositionIn"];
type RoleListOut = components["schemas"]["RoleListOut"];
type RoleOut = components["schemas"]["RoleOut"];
type RoleIn = components["schemas"]["RoleIn"];
type TeamListOut = components["schemas"]["TeamListOut"];
type TeamOut = components["schemas"]["mailbus__api__schemas__contract__org__TeamOut"];
type TeamIn = components["schemas"]["mailbus__api__schemas__contract__org__TeamIn"];
type SeatListOut = components["schemas"]["SeatListOut"];
type SeatOut = components["schemas"]["SeatOut"];
type SeatAssignIn = components["schemas"]["SeatAssignIn"];
type BindingIn = components["schemas"]["BindingIn"];
type PermissionsIn = components["schemas"]["PermissionsIn"];
type PermissionsOut = components["schemas"]["PermissionsOut"];
type RolesIn = components["schemas"]["RolesIn"];
type RolesOut = components["schemas"]["RolesOut"];
type CapabilitiesIn = components["schemas"]["CapabilitiesIn"];
type CapabilitiesOut = components["schemas"]["CapabilitiesOut"];

// === 员工 ===

export function listEmployees(query?: {
  type?: "human" | "agent" | null;
  position_id?: string | null;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (query?.type) params.set("type", query.type);
  if (query?.position_id) params.set("position_id", query.position_id);
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<EmployeeListOut>(q ? `/api/employees?${q}` : "/api/employees");
}

export function getEmployee(employeeId: string) {
  return api<EmployeeOut>(`/api/employees/${encodeURIComponent(employeeId)}`);
}

export function updateEmployee(employeeId: string, body: EmployeeUpdateIn) {
  return api<EmployeeOut>(`/api/employees/${encodeURIComponent(employeeId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteEmployee(employeeId: string) {
  return api(`/api/employees/${encodeURIComponent(employeeId)}`, { method: "DELETE" });
}

export function inviteEmployee(body: EmployeeInviteIn) {
  return api<InviteOut>("/api/employees/invite", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function resendInvite(inviteId: string) {
  return api<InviteOut>(`/api/invites/${encodeURIComponent(inviteId)}/resend`, {
    method: "POST",
  });
}

export function revokeInvite(inviteId: string) {
  return api<InviteOut>(`/api/invites/${encodeURIComponent(inviteId)}/revoke`, {
    method: "POST",
  });
}

// === 员工绑定（权限/角色/技能） ===

export function getEmployeePermissions(employeeId: string) {
  return api<PermissionsOut>(`/api/employees/${encodeURIComponent(employeeId)}/permissions`);
}

export function putEmployeePermissions(employeeId: string, body: PermissionsIn) {
  return api<PermissionsOut>(`/api/employees/${encodeURIComponent(employeeId)}/permissions`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function getEmployeeRoles(employeeId: string) {
  return api<RolesOut>(`/api/employees/${encodeURIComponent(employeeId)}/roles`);
}

export function putEmployeeRoles(employeeId: string, body: RolesIn) {
  return api<RolesOut>(`/api/employees/${encodeURIComponent(employeeId)}/roles`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function getEmployeeCapabilities(employeeId: string) {
  return api<CapabilitiesOut>(`/api/employees/${encodeURIComponent(employeeId)}/capabilities`);
}

export function putEmployeeCapabilities(employeeId: string, body: CapabilitiesIn) {
  return api<CapabilitiesOut>(`/api/employees/${encodeURIComponent(employeeId)}/capabilities`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// === 岗位 ===

export function listPositions(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<PosListOut>(q ? `/api/positions?${q}` : "/api/positions");
}

export function createPosition(body: PositionIn) {
  return api<PositionOut>("/api/positions", { method: "POST", body: JSON.stringify(body) });
}

export function updatePosition(positionId: string, body: PositionIn) {
  return api<PositionOut>(`/api/positions/${encodeURIComponent(positionId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deletePosition(positionId: string) {
  return api(`/api/positions/${encodeURIComponent(positionId)}`, { method: "DELETE" });
}

export function bindPositionEmployees(positionId: string, body: BindingIn) {
  return api<PositionOut>(`/api/positions/${encodeURIComponent(positionId)}/employees`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function bindPositionRoles(positionId: string, body: BindingIn) {
  return api<PositionOut>(`/api/positions/${encodeURIComponent(positionId)}/roles`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// === 角色 ===

export function listRoles(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<RoleListOut>(q ? `/api/roles?${q}` : "/api/roles");
}

export function createRole(body: RoleIn) {
  return api<RoleOut>("/api/roles", { method: "POST", body: JSON.stringify(body) });
}

export function updateRole(roleId: string, body: RoleIn) {
  return api<RoleOut>(`/api/roles/${encodeURIComponent(roleId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRole(roleId: string) {
  return api(`/api/roles/${encodeURIComponent(roleId)}`, { method: "DELETE" });
}

export function bindRoleEmployees(roleId: string, body: BindingIn) {
  return api<RoleOut>(`/api/roles/${encodeURIComponent(roleId)}/employees`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function bindRolePositions(roleId: string, body: BindingIn) {
  return api<RoleOut>(`/api/roles/${encodeURIComponent(roleId)}/positions`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// === 团队 ===

export function listTeams(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<TeamListOut>(q ? `/api/teams?${q}` : "/api/teams");
}

export function createTeam(body: TeamIn) {
  return api<TeamOut>("/api/teams", { method: "POST", body: JSON.stringify(body) });
}

export function updateTeam(teamId: string, body: TeamIn) {
  return api<TeamOut>(`/api/teams/${encodeURIComponent(teamId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteTeam(teamId: string) {
  return api(`/api/teams/${encodeURIComponent(teamId)}`, { method: "DELETE" });
}

export function listTeamSeats(teamId: string) {
  return api<SeatListOut>(`/api/teams/${encodeURIComponent(teamId)}/seats`);
}

export function assignSeat(seatId: string, body: SeatAssignIn) {
  return api<SeatOut>(`/api/seats/${encodeURIComponent(seatId)}/assign`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
