import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 任务管理：创建 → 派发 → 推进/取消；自由任务与流程任务共用一张表。 */

type TaskNode = { node_id: string; name: string; order: number; state: string };

type Task = {
  task_id: string;
  title: string;
  state: string;
  workflow_id?: string | null;
  workflow_version?: number | null;
  owner_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  nodes: TaskNode[];
};

type Tone = "ok" | "warn" | "danger" | "default";

const STATE_TONE: Record<string, Tone> = {
  draft: "default",
  queued: "warn",
  running: "ok",
  blocked: "warn",
  done: "ok",
  failed: "danger",
  cancelled: "default",
};

const OUTCOMES = ["running", "done", "failed", "blocked", "skipped"] as const;

const STATES = ["", "draft", "queued", "running", "blocked", "done", "failed", "cancelled"];

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleTasksPage({ can }: { can: (capability: string) => boolean }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stateFilter, setStateFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [selected, setSelected] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [title, setTitle] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [workflowVersion, setWorkflowVersion] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [outcome, setOutcome] = useState<string>("running");

  const load = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (stateFilter) params.set("state", stateFilter);
    if (ownerFilter.trim()) params.set("owner_id", ownerFilter.trim());
    const query = params.toString();
    const result = await api<Task[]>(`/api/tasks${query ? `?${query}` : ""}`);
    setLoading(false);
    if (result.ok) {
      setTasks(result.data);
      setErr("");
    } else {
      setTasks([]);
      setErr(result.error);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function create() {
    setErr("");
    setMsg("");
    if (!title.trim()) {
      setErr("任务标题不能为空");
      return;
    }
    const result = await api<Task>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: title.trim(),
        owner_id: ownerId.trim() || null,
        workflow_id: workflowId.trim() || null,
        workflow_version: workflowVersion.trim() ? Number(workflowVersion) : null,
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已创建任务「${result.data.title}」`);
    setTitle("");
    setSelected(result.data);
    await load();
  }

  async function act(task: Task, action: "dispatch" | "cancel") {
    setErr("");
    setMsg("");
    const result = await api<Task>(
      `/api/tasks/${encodeURIComponent(task.task_id)}/${action}`,
      { method: "POST" },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(
      action === "dispatch"
        ? `已派发「${task.title}」`
        : `已取消「${task.title}」`,
    );
    await load();
  }

  async function advance(task: Task) {
    setErr("");
    setMsg("");
    const result = await api<Task>(
      `/api/tasks/${encodeURIComponent(task.task_id)}/advance`,
      {
        method: "POST",
        body: JSON.stringify({ node_id: nodeId || null, outcome }),
      },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setSelected(result.data);
    setMsg(`已推进「${task.title}」→ ${result.data.state}`);
    await load();
  }

  return (
    <>
      <ConsolePageHeader
        title="任务"
        description="创建、派发、推进与取消任务；流程任务按节点执行，自由任务直接改任务状态"
      />

      <ConsoleSection title="新建任务">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            标题
            <input
              className="mt-1 block w-56 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="必填"
            />
          </label>
          <label className="text-[11px] text-mute">
            负责人
            <input
              className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
              placeholder="留空 = 自己"
            />
          </label>
          <label className="text-[11px] text-mute">
            流程
            <input
              className="mt-1 block w-36 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={workflowId}
              onChange={(e) => setWorkflowId(e.target.value)}
              placeholder="可选"
            />
          </label>
          <label className="text-[11px] text-mute">
            版本
            <input
              className="mt-1 block w-20 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={workflowVersion}
              onChange={(e) => setWorkflowVersion(e.target.value)}
              placeholder="最新"
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!can("task_create")}
            onClick={() => void create()}
          >
            创建
          </button>
        </div>
      </ConsoleSection>

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-mute">
          状态
          <select
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
          >
            {STATES.map((state) => (
              <option key={state || "all"} value={state}>
                {state || "全部"}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-mute">
          负责人
          <input
            className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            placeholder="employee_id"
          />
        </label>
        <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
          查询
        </button>
      </div>

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection title={`任务（${tasks.length}）`}>
        <ConsoleTable
          rows={tasks}
          rowKey={(row) => row.task_id}
          loading={loading}
          empty="暂无任务"
          onRowClick={(row) => {
            setSelected(row);
            setNodeId("");
          }}
          selectedKey={selected?.task_id}
          columns={[
            { key: "title", header: "标题", render: (row) => row.title },
            {
              key: "state",
              header: "状态",
              render: (row) => (
                <ConsoleTag tone={STATE_TONE[row.state] || "default"}>{row.state}</ConsoleTag>
              ),
            },
            {
              key: "owner",
              header: "负责人",
              render: (row) => (
                <span className="font-mono text-[11px]">{row.owner_id || "—"}</span>
              ),
            },
            {
              key: "workflow",
              header: "流程",
              render: (row) =>
                row.workflow_id ? (
                  <span className="font-mono text-[11px] text-mute">
                    {row.workflow_id} v{row.workflow_version}
                  </span>
                ) : (
                  <span className="text-mute">自由任务</span>
                ),
            },
            {
              key: "updated",
              header: "更新时间",
              render: (row) => (
                <span className="text-[11px] text-mute">{timeText(row.updated_at)}</span>
              ),
            },
            {
              key: "act",
              header: "操作",
              render: (row) => (
                <span className="flex gap-1.5">
                  <button
                    type="button"
                    className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
                    disabled={!can("task_dispatch")}
                    onClick={() => void act(row, "dispatch")}
                  >
                    派发
                  </button>
                  <button
                    type="button"
                    className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                    disabled={!can("task_dispatch")}
                    onClick={() => void act(row, "cancel")}
                  >
                    取消
                  </button>
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {selected && (
        <ConsoleSection title={`推进 · ${selected.title}（${selected.state}）`}>
          <div className="mb-3 flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-mute">
              节点
              <select
                className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
              >
                <option value="">自动选择当前节点</option>
                {selected.nodes.map((node) => (
                  <option key={node.node_id} value={node.node_id}>
                    {node.order}. {node.name}（{node.state}）
                  </option>
                ))}
              </select>
            </label>
            <label className="text-[11px] text-mute">
              动作
              <select
                className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                {OUTCOMES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={!can("result_submit")}
              onClick={() => void advance(selected)}
            >
              推进
            </button>
          </div>

          {selected.nodes.length > 0 && (
            <ConsoleTable
              rows={selected.nodes}
              rowKey={(node) => node.node_id}
              empty="自由任务没有节点"
              columns={[
                { key: "order", header: "#", render: (node) => String(node.order) },
                { key: "name", header: "节点", render: (node) => node.name },
                {
                  key: "state",
                  header: "状态",
                  render: (node) => (
                    <ConsoleTag tone={STATE_TONE[node.state] || "default"}>
                      {node.state}
                    </ConsoleTag>
                  ),
                },
              ]}
            />
          )}
        </ConsoleSection>
      )}
    </>
  );
}
