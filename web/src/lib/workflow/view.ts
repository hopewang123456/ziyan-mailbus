import type { components } from "../contracts";

/**
 * 工作流域视图模型：DTO → Row / 编辑器状态。
 */

/**
 * 节点类型直接派生自生成契约（GraphNodeIn.node_type），
 * 不再本地重复声明枚举，避免与后端真相源分叉。
 */
export type NodeType = components["schemas"]["GraphNodeIn"]["node_type"];

export interface NodeRow {
  id: string;            // node_id
  type: NodeType;
  name: string;
  seq: number;
  x: number;             // pos_x
  y: number;             // pos_y
  maxLoops: number;
  maxRetries: number;
  timeoutSeconds?: number | null;
  positionId?: string | null;
  needsArtifactsFrom: string[];
  promptTemplate?: string | null;
  config?: Record<string, unknown> | null;
}

export interface EdgeRow {
  id: string;            // 构造自 from_node_id → to_node_id
  from: string;
  to: string;
  condition?: string | null;
}

export interface GraphRow {
  revision: number;
  nodes: NodeRow[];
  edges: EdgeRow[];
}

export interface WorkflowRow {
  id: string;            // workflow_id
  name: string;
  latestVersion: number;
  publishedVersion?: number | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface VersionRow {
  version: number;
  state: string;
  revision: number;
  workflowId: string;
  createdAt?: string | null;
  publishedAt?: string | null;
}

export interface ValidateIssueRow {
  code: string;
  messageZh: string;
  nodeId?: string | null;
}

// === 映射 ===

export function mapWorkflow(w: components["schemas"]["WorkflowOut"]): WorkflowRow {
  return {
    id: w.workflow_id,
    name: w.name,
    latestVersion: w.latest_version,
    publishedVersion: w.published_version,
    createdAt: w.created_at,
    updatedAt: w.updated_at,
  };
}

export function mapVersion(v: components["schemas"]["VersionOut"]): VersionRow {
  return {
    version: v.version,
    state: v.state,
    revision: v.revision,
    workflowId: v.workflow_id,
    createdAt: v.created_at,
    publishedAt: v.published_at,
  };
}

export function mapGraph(g: components["schemas"]["GraphOut"]): GraphRow {
  const nodes = (g.graph.nodes ?? []).map((n) => ({
    id: n.node_id,
    type: n.node_type,
    name: n.name,
    seq: n.seq,
    x: n.pos_x,
    y: n.pos_y,
    maxLoops: n.max_loops,
    maxRetries: n.max_retries,
    timeoutSeconds: n.timeout_seconds,
    positionId: n.position_id,
    needsArtifactsFrom: n.needs_artifacts_from ?? [],
    promptTemplate: n.prompt_template,
    config: n.config ?? null,
  }));

  const edges = (g.graph.edges ?? []).map((e) => ({
    id: `${e.from_node_id}→${e.to_node_id}`,
    from: e.from_node_id,
    to: e.to_node_id,
    condition: e.condition,
  }));

  return { revision: g.revision, nodes, edges };
}

export function mapValidateIssue(issue: components["schemas"]["ValidateIssueOut"]): ValidateIssueRow {
  return {
    code: issue.code,
    messageZh: issue.message_zh,
    nodeId: issue.node_id,
  };
}

// === 反向：构造请求 DTO ===

export function buildGraphIn(graph: GraphRow, revision: number): components["schemas"]["GraphIn"] {
  return {
    revision,
    graph: {
      nodes: graph.nodes.map((n) => ({
        node_id: n.id,
        node_type: n.type,
        name: n.name,
        seq: n.seq,
        pos_x: n.x,
        pos_y: n.y,
        max_loops: n.maxLoops,
        max_retries: n.maxRetries,
        timeout_seconds: n.timeoutSeconds ?? null,
        position_id: n.positionId ?? null,
        needs_artifacts_from: n.needsArtifactsFrom,
        prompt_template: n.promptTemplate ?? null,
        config: n.config ?? null,
      })),
      edges: graph.edges.map((e) => ({
        from_node_id: e.from,
        to_node_id: e.to,
        condition: e.condition ?? null,
      })),
    },
  };
}

// === 状态 ===

export const VERSION_STATE_LABELS: Record<string, { label: string; tone: "ok" | "warn" | "danger" | "default" }> = {
  published: { label: "已发布", tone: "ok" },
  draft: { label: "草稿", tone: "warn" },
  archived: { label: "已归档", tone: "default" },
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  start: "开始",
  agent: "Agent",
  human: "人工",
  condition: "条件",
  parallel_join: "汇聚",
  final_approval: "终验",
};

export const NODE_TEMPLATE: NodeType[] = [
  "start",
  "agent",
  "human",
  "condition",
  "parallel_join",
  "final_approval",
];
