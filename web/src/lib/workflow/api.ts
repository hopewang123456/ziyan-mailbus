import { api } from "../api";
import type { components } from "../contracts";

/**
 * 工作流域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type WorkflowListOut = components["schemas"]["WorkflowListOut"];
type WorkflowOut = components["schemas"]["WorkflowOut"];
type WorkflowIn = components["schemas"]["WorkflowIn"];
type VersionListOut = components["schemas"]["VersionListOut"];
type VersionOut = components["schemas"]["VersionOut"];
type GraphOut = components["schemas"]["GraphOut"];
type GraphIn = components["schemas"]["GraphIn"];
type ValidateOut = components["schemas"]["ValidateOut"];

export function listWorkflows(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit) params.set("limit", String(query.limit));
  if (query?.offset) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<WorkflowListOut>(q ? `/api/workflows?${q}` : "/api/workflows");
}

export function getWorkflow(workflowId: string) {
  return api<WorkflowOut>(`/api/workflows/${encodeURIComponent(workflowId)}`);
}

export function createWorkflow(body: WorkflowIn) {
  return api<WorkflowOut>("/api/workflows", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteWorkflow(workflowId: string) {
  return api(`/api/workflows/${encodeURIComponent(workflowId)}`, { method: "DELETE" });
}

export function listVersions(workflowId: string) {
  return api<VersionListOut>(`/api/workflows/${encodeURIComponent(workflowId)}/versions`);
}

export function cloneVersion(workflowId: string, version: number) {
  return api<VersionOut>(
    `/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}/clone`,
    { method: "POST" },
  );
}

export function getGraph(workflowId: string, version: number) {
  return api<GraphOut>(
    `/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}/graph`,
  );
}

export function saveGraph(workflowId: string, version: number, body: GraphIn) {
  return api<GraphOut>(
    `/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}/graph`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export function validateGraph(workflowId: string, version: number, body: GraphIn | null) {
  return api<ValidateOut>(
    `/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}/validate`,
    {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    },
  );
}

export function publishVersion(workflowId: string, version: number) {
  return api<VersionOut>(
    `/api/workflows/${encodeURIComponent(workflowId)}/versions/${version}/publish`,
    { method: "POST" },
  );
}
