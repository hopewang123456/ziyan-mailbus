import { api, downloadFile } from "../api";
import type { components } from "../contracts";

/**
 * 任务域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type TaskListOut = components["schemas"]["TaskListOut"];
type TaskDetailOut = components["schemas"]["TaskDetailOut"];
type TaskCountersOut = components["schemas"]["TaskCountersOut"];
type TaskTraceOut = components["schemas"]["TaskTraceOut"];
type CancelIn = components["schemas"]["CancelIn"];
type ResultIn = components["schemas"]["ResultIn"];
type RerunJoinIn = components["schemas"]["RerunJoinIn"];
type TaskCreateIn = components["schemas"]["TaskCreateIn"];
type ApprovalListOut = components["schemas"]["ApprovalListOut"];
type ApprovalOut = components["schemas"]["ApprovalOut"];
type ResolveIn = components["schemas"]["ResolveIn"];
type ArtifactOut = components["schemas"]["ArtifactOut"];

export interface ListTasksQuery {
  state?: string | null;
  owner_id?: string | null;
  workflow_id?: string | null;
  limit?: number;
  offset?: number;
}

export function listTasks(query: ListTasksQuery = {}) {
  const params = new URLSearchParams();
  if (query.state) params.set("state", query.state);
  if (query.owner_id) params.set("owner_id", query.owner_id);
  if (query.workflow_id) params.set("workflow_id", query.workflow_id);
  params.set("limit", String(query.limit ?? 100));
  params.set("offset", String(query.offset ?? 0));
  return api<TaskListOut>(`/api/tasks?${params.toString()}`);
}

export function getTask(taskId: string) {
  return api<TaskDetailOut>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function createTask(body: TaskCreateIn) {
  return api<TaskDetailOut>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ListApprovalsQuery {
  state?: string | null;
  limit?: number;
  offset?: number;
}

export function listApprovals(query: ListApprovalsQuery = {}) {
  const params = new URLSearchParams();
  if (query.state) params.set("state", query.state);
  params.set("limit", String(query.limit ?? 100));
  params.set("offset", String(query.offset ?? 0));
  return api<ApprovalListOut>(`/api/approvals?${params.toString()}`);
}

export function getApproval(approvalId: string) {
  return api<ApprovalOut>(`/api/approvals/${encodeURIComponent(approvalId)}`);
}

export function resolveApproval(approvalId: string, body: ResolveIn) {
  return api<ApprovalOut>(`/api/approvals/${encodeURIComponent(approvalId)}/resolve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelTask(taskId: string, body: CancelIn | null = null) {
  return api<TaskDetailOut>(
    `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
    {
      method: "POST",
      body: body ? JSON.stringify(body) : "null",
    },
  );
}

export function claimNode(taskId: string, nodeId: string) {
  return api<TaskDetailOut>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/claim`,
    { method: "POST" },
  );
}

export function submitResult(taskId: string, nodeId: string, body: ResultIn) {
  return api<TaskDetailOut>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/result`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function rerunJoin(taskId: string, nodeId: string, body: RerunJoinIn) {
  return api<TaskDetailOut>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/rerun-join`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function getTaskTrace(taskId: string) {
  return api<TaskTraceOut>(`/api/tasks/${encodeURIComponent(taskId)}/trace`);
}

/** 上传任务节点产物（multipart），返回新建的 ArtifactOut。 */
export function uploadArtifact(
  taskId: string,
  nodeId: string,
  file: File,
  description?: string | null,
) {
  const form = new FormData();
  form.append("file", file);
  if (description) form.append("description", description);
  return api<ArtifactOut>(
    `/api/tasks/${encodeURIComponent(taskId)}/nodes/${encodeURIComponent(nodeId)}/artifacts`,
    { method: "POST", body: form },
  );
}

export function getArtifact(
  artifactId: string,
  options: { filename?: string; resign?: () => Promise<string> } = {},
) {
  const url = `/api/artifacts/${encodeURIComponent(artifactId)}/download`;
  return downloadFile(url, options);
}

export function summary() {
  return api<TaskCountersOut>("/api/tasks/summary");
}
