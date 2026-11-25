import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Position,
  Handle,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ConsolePageHeader, ConsoleSection, ConsoleTag } from "../../components/console/ConsoleKit";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { NODE_TYPE_LABELS, NODE_TEMPLATE, buildGraphIn, type NodeType } from "../../lib/workflow/view";
import type { GraphRow } from "../../lib/workflow/view";
import { useWorkflow, useGraph } from "../../lib/workflow/hooks";
import { cloneVersion, getGraph, publishVersion, saveGraph, validateGraph } from "../../lib/workflow/api";

interface Props {
  workflowId: string;
  version: number;
  canModify: boolean;
  canPublish: boolean;
}

/**
 * 工作流编辑器：React Flow + Graph 读写 + revision CAS + 发布校验。
 * 节点类型：start / agent / human / condition / parallel_join / final_approval。
 * 连线规则：condition 允许多出边 + condition；parallel_join 允许多入边。
 */
export function WorkflowEditorPage({ workflowId, version, canModify, canPublish }: Props) {
  const navigate = useNavigate();
  const workflow = useWorkflow(workflowId);
  const { data: graph, loading, error } = useGraph(workflowId, version);
  const isPublished = workflow.data?.publishedVersion === version;
  const canEdit = canModify && !isPublished;

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [revision, setRevision] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [savingErr, setSavingErr] = useState("");
  const [savingMsg, setSavingMsg] = useState("");

  const [, setValidating] = useState(false);
  const [validateErr, setValidateErr] = useState("");
  const [validateMsg, setValidateMsg] = useState("");

  // 409 时展示服务端 revision 让用户决定 force 与否
  const [conflictRevision, setConflictRevision] = useState<number | null>(null);

  // === 加载后初始化 React Flow 状态 ===
  useEffect(() => {
    if (!graph) return;
    setRevision(graph.revision);
    setNodes(graph.nodes.map(toFlowNode));
    setEdges(graph.edges.map(toFlowEdge));
    setDirty(false);
    setSelectedNode(null);
    setConflictRevision(null);
  }, [graph]);

  // === React Flow 事件 ===
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const mutable = changes.filter((change) => change.type !== "select" && change.type !== "dimensions");
      if (mutable.length > 0 && !canEdit) return;
      setNodes((ns) => applyNodeChanges(changes, ns));
      if (mutable.length > 0) setDirty(true);
    },
    [canEdit],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const mutable = changes.filter((change) => change.type !== "select");
      if (mutable.length > 0 && !canEdit) return;
      setEdges((es) => applyEdgeChanges(changes, es));
      if (mutable.length > 0) setDirty(true);
    },
    [canEdit],
  );
  const onConnect = useCallback(
    (conn: Connection) => {
      if (!canEdit) return;
      setEdges((es) => addEdge({ ...conn, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed } }, es));
      setDirty(true);
    },
    [canEdit],
  );
  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelectedNode(node.id);
  }, []);

  // === 加节点 ===
  function addNode(type: NodeType) {
    if (!canEdit) return;
    const nid = `n_${Date.now().toString(36)}_${Math.floor(Math.random() * 1000)}`;
    const seq = nodes.length;
    setNodes((ns) => [
      ...ns,
      {
        id: nid,
        type: "wfNode",
        position: { x: 200 + seq * 120, y: 120 },
        data: {
          nodeType: type,
          name: NODE_TYPE_LABELS[type],
          seq,
          maxLoops: 3,
          maxRetries: 3,
          timeoutSeconds: null,
          positionId: null,
          needsArtifactsFrom: [],
          promptTemplate: null,
        },
      },
    ]);
    setDirty(true);
    setSelectedNode(nid);
  }

  function removeNode(id: string) {
    if (!canEdit) return;
    setNodes((ns) => ns.filter((n) => n.id !== id));
    setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
    if (selectedNode === id) setSelectedNode(null);
    setDirty(true);
  }

  function removeEdge(id: string) {
    if (!canEdit) return;
    setEdges((es) => es.filter((e) => e.id !== id));
    setDirty(true);
  }

  // === 视图 → GraphRow ===
  const currentGraph = useCallback((): GraphRow => {
    return {
      revision,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: (n.data as any).nodeType as NodeType,
        name: (n.data as any).name as string,
        seq: (n.data as any).seq as number,
        x: n.position.x,
        y: n.position.y,
        maxLoops: (n.data as any).maxLoops as number,
        maxRetries: (n.data as any).maxRetries as number,
        timeoutSeconds: (n.data as any).timeoutSeconds as number | null | undefined,
        positionId: (n.data as any).positionId as string | null | undefined,
        needsArtifactsFrom: (n.data as any).needsArtifactsFrom as string[],
        promptTemplate: (n.data as any).promptTemplate as string | null | undefined,
        config: null,
      })),
      edges: edges.map((e) => ({
        id: `${e.source}→${e.target}`,
        from: e.source,
        to: e.target,
        condition: (e.label as string | undefined) ?? null,
      })),
    };
  }, [nodes, edges, revision]);

  // === 保存 ===
  async function save(force = false) {
    if (!canEdit) return;
    setSaving(true);
    setSavingErr("");
    setSavingMsg("");
    setConflictRevision(null);

    const targetRev = force && conflictRevision !== null ? conflictRevision : revision;
    const body = buildGraphIn(currentGraph(), targetRev);
    const result = await saveGraph(workflowId, version, body);
    setSaving(false);

    if (!result.ok) {
      if (result.status === 409 && typeof result.data === "object" && result.data) {
        // CAS 冲突，后端返回最新 revision
        const latest = (result.data as any).revision;
        setConflictRevision(typeof latest === "number" ? latest : null);
        setSavingErr(`版本冲突（服务端 revision=${latest ?? "?"}）。可强制覆盖或重新拉取。`);
      } else if (result.status === 422) {
        setSavingErr(`校验未通过：${result.error}`);
      } else {
        setSavingErr(result.error);
      }
      return;
    }

    if (result.data) {
      setRevision(result.data.revision);
      setNodes((result.data.graph.nodes ?? []).map(toFlowNode));
      setEdges((result.data.graph.edges ?? []).map(toFlowEdge));
    }
    setDirty(false);
    setSavingMsg(`已保存，revision=${result.data?.revision ?? "?"}`);
  }

  async function refreshFromServer() {
    setSavingErr("");
    setSavingMsg("");
    const result = await getGraph(workflowId, version);
    if (result.ok) {
      setRevision(result.data.revision);
      setNodes((result.data.graph.nodes ?? []).map(toFlowNode));
      setEdges((result.data.graph.edges ?? []).map(toFlowEdge));
      setDirty(false);
      setConflictRevision(null);
      setSavingMsg("已重新拉取服务端版本");
    } else {
      setSavingErr(result.error ?? "拉取失败");
    }
  }

  // === 校验 ===
  async function validate() {
    setValidating(true);
    setValidateErr("");
    setValidateMsg("");
    const body = buildGraphIn(currentGraph(), revision);
    const result = await validateGraph(workflowId, version, body);
    setValidating(false);
    if (!result.ok) { setValidateErr(result.error); return; }
    const v = result.data;
    if (!v) return;
    if (v.ok && !v.errors?.length) setValidateMsg("校验通过 ✓");
    else {
      const errors = v.errors ?? [];
      const warnings = v.warnings ?? [];
      setValidateMsg(
        [`${errors.length} 错误`, `${warnings.length} 警告`].join(" · ")
      );
      setValidateErr(errors.map((e: any) => `${e.node_id ? `[${e.node_id}] ` : ""}${e.message_zh}`).join("\n") || "校验未通过");
    }
  }

  // === 发布 ===
  async function publish() {
    if (!canPublish) return;
    setSaving(true);
    setSavingErr("");
    setSavingMsg("");
    const result = await publishVersion(workflowId, version);
    setSaving(false);
    if (!result.ok) {
      if (result.status === 409) setSavingErr("版本冲突；请先校验并保存最新 Graph 后发布。");
      else setSavingErr(result.error);
      return;
    }
    setSavingMsg(`已发布 v${version}`);
  }

  // === 派生新版本 ===
  async function cloneLatest() {
    if (!canModify || saving) return;
    setSaving(true);
    setSavingErr("");
    setSavingMsg("");
    const result = await cloneVersion(workflowId, version);
    setSaving(false);
    if (!result.ok) {
      setSavingErr(result.error);
      return;
    }
    navigate(`/console/workflows/${encodeURIComponent(workflowId)}/v/${result.data.version}`);
  }

  if (loading) {
    return (
      <>
        <ConsolePageHeader title="编辑器" description={`${workflowId} · v${version}`} />
        <ConsolePageState kind="loading" title="加载 Graph" description="拉取节点与连线…" />
      </>
    );
  }
  if (error || !graph) {
    return (
      <>
        <ConsolePageHeader title="编辑器" description={`${workflowId} · v${version}`} />
        <ConsolePageState kind="error" title="加载失败" description={error ?? "Graph 为空"} />
      </>
    );
  }

  return (
    <>
      <ConsolePageHeader
        title={workflow.data?.name ?? "加载中…"}
        description={`${workflowId} · v${version} · revision=${revision}${isPublished ? " · 已发布版本只读，派生后可编辑" : ""}`}
      />

      {savingErr && <p className="mb-2 text-xs text-flare whitespace-pre-line">{savingErr}</p>}
      {savingMsg && <p className="mb-2 text-xs text-mint">{savingMsg}</p>}
      {validateErr && <p className="mb-2 text-xs text-flare whitespace-pre-line">{validateErr}</p>}
      {validateMsg && <p className="mb-2 text-xs text-mint">{validateMsg}</p>}

      <ConsoleSection
        title="节点"
        actions={
          <span className="flex items-center gap-2">
            <ConsoleTag tone={dirty ? "warn" : "ok"}>{dirty ? "未保存" : "已同步"}</ConsoleTag>
            <ConsoleTag tone={isPublished ? "ok" : "default"}>{isPublished ? "已发布" : "草稿"}</ConsoleTag>
            {NODE_TEMPLATE.map((t) => (
              <button
                key={t}
                type="button"
                className="rounded border border-rail px-2 py-1 text-[11px] text-frost hover:bg-rail/30 disabled:opacity-40"
                disabled={!canEdit}
                onClick={() => addNode(t)}
              >
                + {NODE_TYPE_LABELS[t]}
              </button>
            ))}
            <div className="mx-1 h-4 w-px bg-rail" />
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-[11px] text-mute hover:text-frost"
              disabled={!canEdit || !dirty || saving}
              onClick={() => void save(false)}
            >
              保存 revision={revision}
            </button>
            {conflictRevision !== null && (
              <button
                type="button"
                className="rounded border border-flare/40 px-2 py-1 text-[11px] text-flare hover:bg-flare/10"
                disabled={saving}
                onClick={() => void save(true)}
              >
                强制覆盖（服务端 revision={conflictRevision}）
              </button>
            )}
            {conflictRevision !== null && (
              <button
                type="button"
                className="rounded border border-rail px-2 py-1 text-[11px] text-mute hover:text-frost"
                onClick={() => void refreshFromServer()}
              >
                丢弃本地重新拉取
              </button>
            )}
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-[11px] text-mute hover:text-frost"
              disabled={!canModify || dirty}
              onClick={() => void validate()}
            >
              校验
            </button>
            <button
              type="button"
              className="rounded border border-mint/50 px-2 py-1 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
              disabled={!canPublish || isPublished || dirty || saving}
              onClick={() => void publish()}
            >
              发布 v{version}
            </button>
            <button
              type="button"
              className="rounded border border-rail px-2 py-1 text-[11px] text-mute hover:text-frost disabled:opacity-40"
              disabled={!canModify || saving}
              onClick={() => void cloneLatest()}
            >
              派生新版本
            </button>
          </span>
        }
      >
        <div style={{ height: 540 }} className="rounded border border-rail bg-hull/30">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodesDraggable={canEdit}
            nodesConnectable={canEdit}
            deleteKeyCode={canEdit ? ["Backspace", "Delete"] : null}
            nodeTypes={{ wfNode: WfNode }}
            fitView
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
      </ConsoleSection>

      <div className="grid gap-3 lg:grid-cols-2">
        <NodeInspector
          node={nodes.find((n) => n.id === selectedNode) ?? null}
          onChange={(id, patch) => {
            setNodes((ns) => ns.map((n) => n.id === id ? { ...n, data: { ...n.data, ...patch } } : n));
            setDirty(true);
          }}
          onRemove={(id) => removeNode(id)}
          onClose={() => setSelectedNode(null)}
          canModify={canEdit}
        />
        <EdgeList
          edges={edges}
          nodes={nodes}
          onRemove={(id) => removeEdge(id)}
          canModify={canEdit}
        />
      </div>
    </>
  );
}

// === 节点组件 ===

function WfNode({ data, selected }: NodeProps) {
  const d = data as any;
  const typeLabel = NODE_TYPE_LABELS[d.nodeType as NodeType] ?? d.nodeType;
  return (
    <div
      className={`w-52 rounded-lg border px-3 py-2 shadow ${
        selected ? "border-mint bg-hull ring-2 ring-mint/40" : "border-rail bg-hull"
      }`}
    >
      <Handle type="target" position={Position.Left} />
      <p className="font-mono text-[10px] text-mute">{d.nodeType}</p>
      <p className="truncate text-xs text-frost">{d.name || typeLabel}</p>
      <p className="mt-1 text-[10px] text-mute">seq={d.seq} loops={d.maxLoops} retries={d.maxRetries}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

// === 节点属性面板 ===

interface NodeInspectorProps {
  node: Node | null;
  onChange: (id: string, patch: Record<string, unknown>) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
  canModify: boolean;
}

function NodeInspector({ node, onChange, onRemove, onClose, canModify }: NodeInspectorProps) {
  if (!node) {
    return (
      <ConsoleSection title="属性">
        <p className="text-xs text-mute">点击画布上的节点编辑属性</p>
      </ConsoleSection>
    );
  }
  const d = node.data as any;
  return (
    <ConsoleSection
      title="节点属性"
      actions={
        <span className="flex gap-2">
          <button type="button" className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute" onClick={onClose}>
            关闭
          </button>
          {canModify && (
            <button type="button" className="rounded border border-flare/40 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10" onClick={() => onRemove(node.id)}>
              删除
            </button>
          )}
        </span>
      }
    >
      <div className="grid gap-2 text-xs">
        <label className="grid gap-1">
          <span className="text-[11px] text-mute">ID</span>
          <span className="font-mono text-mute">{node.id}</span>
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] text-mute">名称</span>
          <input
            className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
            disabled={!canModify}
            value={d.name}
            onChange={(e) => onChange(node.id, { name: e.target.value })}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] text-mute">节点类型</span>
          <select
            className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
            disabled={!canModify}
            value={d.nodeType}
            onChange={(e) => onChange(node.id, { nodeType: e.target.value as NodeType })}
          >
            {NODE_TEMPLATE.map((t) => (
              <option key={t} value={t}>{NODE_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1">
            <span className="text-[11px] text-mute">seq</span>
            <input
              type="number"
              className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              disabled={!canModify}
              value={d.seq}
              onChange={(e) => onChange(node.id, { seq: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-[11px] text-mute">位置 Id</span>
            <input
              className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              disabled={!canModify}
              value={d.positionId ?? ""}
              onChange={(e) => onChange(node.id, { positionId: e.target.value || null })}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-[11px] text-mute">max_loops</span>
            <input
              type="number"
              className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              disabled={!canModify}
              value={d.maxLoops}
              onChange={(e) => onChange(node.id, { maxLoops: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-[11px] text-mute">max_retries</span>
            <input
              type="number"
              className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              disabled={!canModify}
              value={d.maxRetries}
              onChange={(e) => onChange(node.id, { maxRetries: Number(e.target.value) || 0 })}
            />
          </label>
        </div>
        <label className="grid gap-1">
          <span className="text-[11px] text-mute">Prompt 模板（可选）</span>
          <textarea
            className="h-24 rounded border border-rail bg-hull p-2 text-xs text-frost disabled:opacity-40"
            disabled={!canModify}
            value={d.promptTemplate ?? ""}
            onChange={(e) => onChange(node.id, { promptTemplate: e.target.value || null })}
            placeholder="Agent / approval / human 节点使用"
          />
        </label>
      </div>
    </ConsoleSection>
  );
}

// === 连线列表 ===

interface EdgeListProps {
  edges: Edge[];
  nodes: Node[];
  onRemove: (id: string) => void;
  canModify: boolean;
}

function EdgeList({ edges, nodes, onRemove, canModify }: EdgeListProps) {
  const nameOf = (id: string): string => {
    const found = nodes.find((n) => n.id === id);
    const d = found?.data as Record<string, unknown> | undefined;
    const name = d?.name;
    return typeof name === "string" ? name : id;
  };
  return (
    <ConsoleSection title={`连线（${edges.length}）`}>
      {edges.length === 0 ? (
        <p className="text-xs text-mute">从节点右侧拖到另一节点左侧建立连线</p>
      ) : (
        <ul className="space-y-1">
          {edges.map((e) => (
            <li key={e.id} className="flex items-center justify-between rounded border border-rail bg-hull/40 px-2 py-1 text-xs">
              <span>
                <span className="text-frost">{nameOf(e.source)}</span>
                <span className="mx-1 text-mute">→</span>
                <span className="text-frost">{nameOf(e.target)}</span>
                {e.label && <span className="ml-2 text-mute">条件：{e.label}</span>}
              </span>
              {canModify && (
                <button type="button" className="rounded border border-flare/40 px-1.5 py-0.5 text-[11px] text-flare hover:bg-flare/10" onClick={() => onRemove(e.id)}>
                  删除
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </ConsoleSection>
  );
}

// === helpers ===

function toFlowNode(n: any): Node {
  // 兼容 NodeRow（id/type/x/y/maxLoops…）和后端 DTO（node_id/node_type/pos_x/pos_y/max_loops…）
  return {
    id: n.id ?? n.node_id,
    type: "wfNode",
    position: { x: n.x ?? n.pos_x, y: n.y ?? n.pos_y },
    data: {
      nodeType: n.type ?? n.node_type,
      name: n.name,
      seq: n.seq ?? 0,
      maxLoops: n.maxLoops ?? n.max_loops ?? 3,
      maxRetries: n.maxRetries ?? n.max_retries ?? 3,
      timeoutSeconds: n.timeoutSeconds ?? n.timeout_seconds,
      positionId: n.positionId ?? n.position_id,
      needsArtifactsFrom: n.needsArtifactsFrom ?? n.needs_artifacts_from ?? [],
      promptTemplate: n.promptTemplate ?? n.prompt_template,
    },
  };
}

function toFlowEdge(e: any): Edge {
  return {
    id: `${e.from ?? e.from_node_id}→${e.to ?? e.to_node_id}`,
    source: e.from ?? e.from_node_id,
    target: e.to ?? e.to_node_id,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed },
    label: e.condition ?? undefined,
  };
}
