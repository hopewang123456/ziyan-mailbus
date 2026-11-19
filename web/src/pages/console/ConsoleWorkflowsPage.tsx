import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";

type Workflow = {
  workflow_id: string;
  name: string;
  latest_version: number;
  published_version?: number | null;
  created_at?: string | null;
};

type VersionNode = { node_id: string; name: string; order: number };
type Version = {
  workflow_id: string;
  version: number;
  state: string;
  nodes: VersionNode[];
  created_at?: string | null;
  published_at?: string | null;
};

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** 工作流定义与不可变版本：创建、重命名、草稿和发布均使用当前契约。 */
export function ConsoleWorkflowsPage({ can }: { can: (capability: string) => boolean }) {
  const [rows, setRows] = useState<Workflow[]>([]);
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [newName, setNewName] = useState("");
  const [editName, setEditName] = useState("");
  const [nodeNames, setNodeNames] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function reload() {
    setLoading(true);
    const result = await api<Workflow[]>("/api/workflows");
    setLoading(false);
    if (result.ok) {
      setRows(result.data);
      setErr("");
    } else {
      setErr(result.error);
    }
  }

  async function openWorkflow(workflowId: string) {
    setErr("");
    const [workflowResult, versionResult] = await Promise.all([
      api<Workflow>(`/api/workflows/${encodeURIComponent(workflowId)}`),
      api<Version[]>(`/api/workflows/${encodeURIComponent(workflowId)}/versions`),
    ]);
    if (workflowResult.ok && versionResult.ok) {
      setSelected(workflowResult.data);
      setEditName(workflowResult.data.name);
      setVersions(versionResult.data);
      return;
    }
    const error = !workflowResult.ok ? workflowResult.error : !versionResult.ok ? versionResult.error : "加载失败";
    setErr(error);
  }

  useEffect(() => {
    void reload();
  }, []);

  async function create() {
    const name = newName.trim();
    if (!name || busy) return;
    setBusy(true);
    setErr("");
    const result = await api<Workflow>("/api/workflows", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setNewName("");
    setMsg(`已创建工作流「${name}」，请添加并发布首个版本`);
    await reload();
    await openWorkflow(result.data.workflow_id);
  }

  async function rename() {
    if (!selected || !editName.trim() || busy) return;
    setBusy(true);
    setErr("");
    const result = await api<Workflow>(`/api/workflows/${encodeURIComponent(selected.workflow_id)}`, {
      method: "PATCH",
      body: JSON.stringify({ name: editName.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setSelected(result.data);
    setMsg(`已重命名为「${result.data.name}」`);
    await reload();
  }

  async function remove() {
    if (!selected || busy) return;
    if (!window.confirm(`删除工作流 ${selected.name}？不可恢复。`)) return;
    setBusy(true);
    const result = await api(`/api/workflows/${encodeURIComponent(selected.workflow_id)}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已删除「${selected.name}」`);
    setSelected(null);
    setVersions([]);
    await reload();
  }

  async function addVersion() {
    if (!selected || busy) return;
    const nodes = nodeNames.split("\n").map((name) => name.trim()).filter(Boolean).map((name) => ({ name }));
    if (!nodes.length) {
      setErr("请至少填写一个节点名称");
      return;
    }
    setBusy(true);
    setErr("");
    const result = await api<Version>(`/api/workflows/${encodeURIComponent(selected.workflow_id)}/versions`, {
      method: "POST",
      body: JSON.stringify({ nodes }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setNodeNames("");
    setMsg(`已创建草稿版本 v${result.data.version}`);
    await reload();
    await openWorkflow(selected.workflow_id);
  }

  async function publish(version: number) {
    if (!selected || busy) return;
    setBusy(true);
    setErr("");
    const result = await api<Version>(
      `/api/workflows/${encodeURIComponent(selected.workflow_id)}/versions/${version}/publish`,
      { method: "POST" },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已发布版本 v${version}；运行中任务仍锁定原版本`);
    await reload();
    await openWorkflow(selected.workflow_id);
  }

  return (
    <>
      <ConsolePageHeader
        title="工作流模板"
        description="定义可重命名；节点以不可变版本保存，发布后供新任务使用"
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection
        title={`工作流（${rows.length}）`}
        actions={
          <span className="flex items-center gap-2">
            <input
              className="w-44 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
              placeholder="新工作流名称"
              disabled={!can("workflow_create")}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
            />
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={busy || !can("workflow_create")}
              onClick={() => void create()}
            >
              新建
            </button>
          </span>
        }
      >
        <ConsoleTable
          rows={rows}
          rowKey={(row) => row.workflow_id}
          loading={loading}
          empty="暂无工作流"
          onRowClick={(row) => void openWorkflow(row.workflow_id)}
          selectedKey={selected?.workflow_id}
          columns={[
            { key: "id", header: "ID", render: (row) => <span className="font-mono">{row.workflow_id}</span> },
            { key: "name", header: "名称", render: (row) => row.name },
            { key: "latest", header: "最新版本", render: (row) => `v${row.latest_version}` },
            { key: "published", header: "已发布", render: (row) => row.published_version ? `v${row.published_version}` : "—" },
            { key: "created", header: "创建时间", render: (row) => <span className="text-[11px] text-mute">{timeText(row.created_at)}</span> },
          ]}
        />
      </ConsoleSection>

      {selected && (
        <>
          <ConsoleSection title={`定义 · ${selected.workflow_id}`}>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-mute">
                名称
                <input
                  className="mt-1 block w-64 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost disabled:opacity-40"
                  disabled={!can("workflow_modify")}
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={busy || !can("workflow_modify")}
                onClick={() => void rename()}
              >
                保存名称
              </button>
              <button
                type="button"
                className="rounded border border-rail px-2 py-1 text-xs text-mute hover:text-flare disabled:opacity-40"
                disabled={busy || !can("workflow_modify")}
                onClick={() => void remove()}
              >
                删除
              </button>
            </div>
          </ConsoleSection>

          <ConsoleSection title={`版本（${versions.length}）`}>
            <ConsoleTable
              rows={versions}
              rowKey={(row) => String(row.version)}
              empty="暂无版本"
              columns={[
                { key: "version", header: "版本", render: (row) => `v${row.version}` },
                { key: "state", header: "状态", render: (row) => <ConsoleTag tone={row.state === "published" ? "ok" : "warn"}>{row.state}</ConsoleTag> },
                { key: "nodes", header: "节点", render: (row) => row.nodes.map((node) => `${node.order}.${node.name}`).join(" → ") },
                { key: "created", header: "创建时间", render: (row) => <span className="text-[11px] text-mute">{timeText(row.created_at)}</span> },
                {
                  key: "action",
                  header: "操作",
                  render: (row) => row.state === "published" ? (
                    <span className="text-[11px] text-mute">{timeText(row.published_at)}</span>
                  ) : (
                    <button
                      type="button"
                      className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
                      disabled={busy || !can("workflow_modify")}
                      onClick={() => void publish(row.version)}
                    >
                      发布
                    </button>
                  ),
                },
              ]}
            />
          </ConsoleSection>

          <ConsoleSection title="新增草稿版本">
            <label className="block text-[11px] text-mute">
              节点名称（每行一个，按行顺序执行）
              <textarea
                className="mt-1 h-28 w-full rounded border border-rail bg-hull/40 p-2 text-xs text-frost disabled:opacity-40"
                disabled={!can("workflow_modify")}
                value={nodeNames}
                onChange={(event) => setNodeNames(event.target.value)}
                placeholder={"需求澄清\n实现\n验收"}
              />
            </label>
            <button
              type="button"
              className="hud-btn mt-2 text-xs disabled:opacity-40"
              disabled={busy || !can("workflow_modify")}
              onClick={() => void addVersion()}
            >
              创建草稿
            </button>
          </ConsoleSection>
        </>
      )}
    </>
  );
}
