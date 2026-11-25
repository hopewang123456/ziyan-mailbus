import type { components } from "../contracts";

/**
 * Agent 域视图模型。
 */

export type AgentRow = {
  id: string;
  name: string;
  agentType: string;
  channelType: string;
  framework: string;
  model?: string | null;
  endpoint?: string | null;
  pendingEndpoint?: string | null;
  endpointReviewStatus: string;
  enabled: boolean;
  online: boolean;
  lastSeenAt?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export type AgentInviteRow = {
  id: string;
  agentType: string;
  channelType: string;
  dataScope: string;
  capabilities: string[];
  permissions: string[];
  employeeName?: string | null;
  positionId?: string | null;
  createdAt?: string | null;
  createdBy?: string | null;
  expiresAt?: string | null;
  revokedAt?: string | null;
  usedAt?: string | null;
  usedByAgentId?: string | null;
  // 明文仅创建响应返回一次
  oneTimeCode?: string | null;
};

export const ENDPOINT_REVIEW_LABELS: Record<string, string> = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已拒绝",
};

export const CHANNEL_TYPE_LABELS: Record<string, string> = {
  a2a: "A2A",
  file_bus: "文件总线",
  pull_only: "仅拉取",
};

export function mapAgent(a: components["schemas"]["AgentOut"]): AgentRow {
  return {
    id: a.agent_id,
    name: a.name,
    agentType: a.agent_type,
    channelType: a.channel_type,
    framework: a.framework,
    model: a.model,
    endpoint: a.endpoint,
    pendingEndpoint: a.pending_endpoint,
    endpointReviewStatus: a.endpoint_review_status,
    enabled: a.enabled,
    online: a.online,
    lastSeenAt: a.last_seen_at,
    createdAt: a.created_at,
    updatedAt: a.updated_at,
  };
}

export function mapAgentInvite(i: components["schemas"]["AgentInviteOut"]): AgentInviteRow {
  return {
    id: i.invite_id,
    agentType: i.agent_type,
    channelType: i.channel_type,
    dataScope: i.data_scope,
    capabilities: i.capabilities ?? [],
    permissions: i.permissions ?? [],
    employeeName: i.employee_name,
    positionId: i.position_id,
    createdAt: i.created_at,
    createdBy: i.created_by,
    expiresAt: i.expires_at,
    revokedAt: i.revoked_at,
    usedAt: i.used_at,
    usedByAgentId: i.used_by_agent_id,
    oneTimeCode: i.invite_code ?? null,
  };
}
