import type { components } from "../contracts";

/**
 * 任务域视图模型。
 * 从 contracts 生成 DTO 映射为 UI 友好的结构；
 * 状态文案与 tone 集中管理，避免页面散落字符串。
 */

export type TaskRow = {
  taskId: string;
  title: string;
  state: string;
  ownerId: string | null;
  workflowId: string | null;
  workflowVersion: number | null;
  currentNode: string | null;
  claimable: boolean;
  progressDone: number;
  progressTotal: number;
  createdAt: string | null;
  updatedAt: string | null;
};

export type TaskDetailRow = {
  taskId: string;
  title: string;
  state: string;
  ownerId: string | null;
  createdBy: string | null;
  workflowId: string | null;
  workflowVersion: number | null;
  terminationReason: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  nodes: NodeRow[];
  runs: RunRow[];
  artifacts: ArtifactRow[];
};

export type ArtifactRow = {
  artifactId: string;
  taskId: string;
  nodeId: string | null;
  runId: string | null;
  fileName: string;
  artifactType: string | null;
  description: string | null;
  sizeBytes: number | null;
  createdBy: string | null;
  createdAt: string | null;
};

export type NodeRow = {
  nodeId: string;
  name: string;
  seq: number;
  state: string;
  currentRunId: string | null;
  runs: RunRow[];
};

export type RunRow = {
  runId: string;
  nodeId: string;
  attemptNo: number;
  state: string;
  fanoutGroup: string | null;
  fanoutSlot: number;
  assignedEmployeeId: string | null;
  dispatchedAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  result: string | null;
  durationMs: number | null;
};

export type TraceEventRow = {
  at: string | null;
  kind: string;
  nodeId: string | null;
  runId: string | null;
  attemptNo: number | null;
  detail: Record<string, unknown> | null;
};

export type SummaryRow = {
  approvals: number;
  mineOpen: number;
  claimable: number;
};

export type ApprovalRow = {
  approvalId: string;
  taskId: string;
  nodeId: string | null;
  title: string;
  tier: string;
  note: string | null;
  requesterId: string | null;
  status: string;
  resolutionNote: string | null;
  createdAt: string | null;
  resolvedAt: string | null;
};

export type StateTone = "default" | "ok" | "warn" | "danger";

/** 状态 → ConsoleTag tone。未登记状态回落 default。 */
export const STATE_TONE: Record<string, StateTone> = {
  draft: "default",
  queued: "warn",
  running: "ok",
  blocked: "warn",
  waiting: "warn",
  approval: "warn",
  done: "ok",
  success: "ok",
  failed: "danger",
  error: "danger",
  cancelled: "default",
  skipped: "default",
  suspended: "warn",
};

export function stateTone(state: string): StateTone {
  return STATE_TONE[state] ?? "default";
}

/** 状态中文展示。未登记状态原样显示，避免吞掉后端新值。 */
export const STATE_LABEL: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "执行中",
  blocked: "阻塞",
  waiting: "等待中",
  approval: "审批中",
  done: "已完成",
  success: "成功",
  failed: "失败",
  error: "错误",
  cancelled: "已取消",
  skipped: "已跳过",
  suspended: "已挂起",
};

export function stateLabel(state: string): string {
  return STATE_LABEL[state] ?? state;
}

/** 运行状态 tone（与任务状态共用映射即可，这里保留扩展点）。 */
export function runStateTone(state: string): StateTone {
  return stateTone(state);
}

function computeDurationMs(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
): number | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return null;
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  if (Number.isNaN(end)) return null;
  return Math.max(0, end - start);
}

export function mapTaskSummary(
  t: components["schemas"]["TaskSummaryOut"],
): TaskRow {
  return {
    taskId: t.task_id,
    title: t.title,
    state: t.state,
    ownerId: t.owner_id ?? null,
    workflowId: t.workflow_id ?? null,
    workflowVersion: t.workflow_version ?? null,
    currentNode: t.current_node ?? null,
    claimable: t.claimable ?? false,
    progressDone: t.progress_done ?? 0,
    progressTotal: t.progress_total ?? 0,
    createdAt: t.created_at ?? null,
    updatedAt: t.updated_at ?? null,
  };
}

export function mapRun(r: components["schemas"]["TaskRunOut"]): RunRow {
  return {
    runId: r.run_id,
    nodeId: r.node_id,
    attemptNo: r.attempt_no,
    state: r.state,
    fanoutGroup: r.fanout_group ?? null,
    fanoutSlot: r.fanout_slot ?? 0,
    assignedEmployeeId: r.assigned_employee_id ?? null,
    dispatchedAt: r.dispatched_at ?? null,
    startedAt: r.started_at ?? null,
    completedAt: r.completed_at ?? null,
    result: r.result ?? null,
    durationMs: computeDurationMs(r.started_at, r.completed_at),
  };
}

export function mapNode(
  n: components["schemas"]["TaskNodeOut"],
): NodeRow {
  const runs = (n.runs ?? []).map(mapRun);
  return {
    nodeId: n.node_id,
    name: n.name,
    seq: n.seq,
    state: n.state,
    currentRunId: n.current_run_id ?? null,
    runs,
  };
}

export function mapTaskDetail(
  t: components["schemas"]["TaskDetailOut"],
): TaskDetailRow {
  const nodes = (t.nodes ?? []).map(mapNode);
  const runs = (t.runs ?? []).map(mapRun);
  const artifacts = (t.artifacts ?? []).map(mapArtifact);
  return {
    taskId: t.task_id,
    title: t.title,
    state: t.state,
    ownerId: t.owner_id ?? null,
    createdBy: t.created_by ?? null,
    workflowId: t.workflow_id ?? null,
    workflowVersion: t.workflow_version ?? null,
    terminationReason: t.termination_reason ?? null,
    createdAt: t.created_at ?? null,
    updatedAt: t.updated_at ?? null,
    nodes,
    runs,
    artifacts,
  };
}

export function mapArtifact(
  a: components["schemas"]["ArtifactOut"],
): ArtifactRow {
  return {
    artifactId: a.artifact_id,
    taskId: a.task_id,
    nodeId: a.node_id ?? null,
    runId: a.run_id ?? null,
    fileName: a.file_name,
    artifactType: a.artifact_type ?? null,
    description: a.description ?? null,
    sizeBytes: a.size_bytes ?? null,
    createdBy: a.created_by ?? null,
    createdAt: a.created_at ?? null,
  };
}

export function mapTraceEvent(
  e: components["schemas"]["TaskTraceEventOut"],
): TraceEventRow {
  return {
    at: e.at ?? null,
    kind: e.kind,
    nodeId: e.node_id ?? null,
    runId: e.run_id ?? null,
    attemptNo: e.attempt_no ?? null,
    detail: (e.detail as Record<string, unknown> | null) ?? null,
  };
}

export function mapSummary(
  s: components["schemas"]["TaskCountersOut"],
): SummaryRow {
  return {
    approvals: s.approvals ?? 0,
    mineOpen: s.mine_open ?? 0,
    claimable: s.claimable ?? 0,
  };
}

export function mapApproval(a: components["schemas"]["ApprovalOut"]): ApprovalRow {
  return {
    approvalId: a.approval_id,
    taskId: a.task_id,
    nodeId: a.node_id ?? null,
    title: a.title,
    tier: a.tier,
    note: a.note ?? null,
    requesterId: a.requester_id ?? null,
    status: a.status,
    resolutionNote: a.resolution_note ?? null,
    createdAt: a.created_at ?? null,
    resolvedAt: a.resolved_at ?? null,
  };
}
