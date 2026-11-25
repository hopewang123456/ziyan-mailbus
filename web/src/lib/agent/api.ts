import { api } from "../api";
import type { components } from "../contracts";

/**
 * Agent 域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type AgentListOut = components["schemas"]["AgentListOut"];
type AgentOut = components["schemas"]["AgentOut"];
type AgentInviteIn = components["schemas"]["AgentInviteIn"];
type AgentInviteOut = components["schemas"]["AgentInviteOut"];
type AgentInviteListOut = components["schemas"]["AgentInviteListOut"];
type EndpointDecisionIn = components["schemas"]["EndpointDecisionIn"] | null;
type AgentHealthOut = components["schemas"]["AgentHealthOut"];
type AgentTokenOut = components["schemas"]["AgentTokenOut"];

export function listAgents(query?: { enabled?: boolean | null; limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.enabled !== undefined && query?.enabled !== null) params.set("enabled", String(query.enabled));
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<AgentListOut>(q ? `/api/agents?${q}` : "/api/agents");
}

export function getAgent(agentId: string) {
  return api<AgentOut>(`/api/agents/${encodeURIComponent(agentId)}`);
}

export function deleteAgent(agentId: string) {
  return api(`/api/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
}

export function approveEndpoint(agentId: string, note?: string) {
  const body: EndpointDecisionIn = note ? { note } : null;
  return api<AgentOut>(`/api/agents/${encodeURIComponent(agentId)}/endpoint/approve`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function rejectEndpoint(agentId: string, note?: string) {
  const body: EndpointDecisionIn = note ? { note } : null;
  return api<AgentOut>(`/api/agents/${encodeURIComponent(agentId)}/endpoint/reject`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function agentHealth(agentId: string) {
  return api<AgentHealthOut>(`/api/agents/${encodeURIComponent(agentId)}/health`, {
    method: "POST",
  });
}

export function rotateToken(agentId: string) {
  return api<AgentTokenOut>(`/api/agents/${encodeURIComponent(agentId)}/rotate-token`, {
    method: "POST",
  });
}

export function revokeToken(agentId: string) {
  return api<AgentOut>(`/api/agents/${encodeURIComponent(agentId)}/revoke-token`, {
    method: "POST",
  });
}

export function unbindAgent(agentId: string) {
  return api<AgentOut>(`/api/agents/${encodeURIComponent(agentId)}/unbind`, {
    method: "POST",
  });
}

// === Agent 邀请码 ===

export function listAgentInvites(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<AgentInviteListOut>(q ? `/api/agent-invites?${q}` : "/api/agent-invites");
}

export function createAgentInvite(body: AgentInviteIn) {
  return api<AgentInviteOut>("/api/agent-invites", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function revokeAgentInvite(inviteId: string) {
  return api<AgentInviteOut>(`/api/agent-invites/${encodeURIComponent(inviteId)}/revoke`, {
    method: "POST",
  });
}
