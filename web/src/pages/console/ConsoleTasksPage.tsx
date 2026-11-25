import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { ConsoleTabs, useTabParam } from "../../components/console/ConsoleTabs";
import { ConfirmDialog, Dialog } from "../../components/console/ConsoleDialog";
import { useTasks, useSummary, useApprovals } from "../../lib/task/hooks";
import { createTask, cancelTask as apiCancelTask, claimNode as apiClaimNode } from "../../lib/task/api";
import { useWorkflows } from "../../lib/workflow/hooks";
import { stateTone, stateLabel } from "../../lib/task/view";
import type { ListTasksQuery } from "../../lib/task/api";
import type { ApprovalRow } from "../../lib/task/view";
import { useConsoleAccess } from "../../lib/console-access";
import { formatDateTime } from "../../lib/format";

const TABS = ["all", "mine", "approvals"] as const;
type TabKey = (typeof TABS)[number];

const STATE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "draft", label: "草稿" },
  { value: "queued", label: "排队中" },
  { value: "running", label: "执行中" },
  { value: "waiting", label: "等待中" },
  { value: "approval", label: "审批中" },
  { value: "blocked", label: "阻塞" },
  { value: "done", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

export function ConsoleTasksPage({ can }: { can: (capability: string) => boolean }) {
  const access = useConsoleAccess();
  const navigate = useNavigate();
  const [tab, setTab] = useTabParam<TabKey>(TABS, "all");
  const canResolve = can("hitl_resolve");

  const [stateFilter, setStateFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [workflowFilter, setWorkflowFilter] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [cancelling, setCancelling] = useState<{ taskId: string; title: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const summary = useSummary();

  const baseQuery: ListTasksQuery = useMemo(() => {
    const q: ListTasksQuery = { limit: 100, offset: 0 };
    if (tab === "mine" && access.employeeId) q.owner_id = access.employeeId;
    else if (tab === "all") {
      if (ownerFilter.trim()) q.owner_id = ownerFilter.trim();
      if (workflowFilter.trim()) q.workflow_id = workflowFilter.trim();
    }
    if (stateFilter && tab === "all") q.state = stateFilter;
    return q;
  }, [tab, stateFilter, ownerFilter, workflowFilter, access.employeeId]);

  const tasks = useTasks(baseQuery, tab !== "approvals");
  const approvals = useApprovals(
    { state: "pending", limit: 100, offset: 0 },
    tab === "approvals" && canResolve,
  );

  const tabsWithBadges = useMemo(() => {
    const counters = summary.data;
    const tabs: { key: TabKey; label: string; badge?: number }[] = [
      { key: "all", label: "全部" },
      { key: "mine", label: "我的工作", badge: counters ? counters.mineOpen : undefined },
    ];
    if (canResolve) {
      tabs.push({ key: "approvals", label: "审批", badge: counters?.approvals });
    }
    return tabs;
  }, [summary.data, canResolve]);

  async function handleCancelReasoned(reason: string) {
    if (!cancelling) return;
    setBusy(true);
    const result = await apiCancelTask(cancelling.taskId, { reason });
    setBusy(false);
    if (!result.ok) {
      setFlash({ kind: "err", text: result.error ?? "取消失败" });
    } else {
      setFlash({ kind: "ok", text: `已取消「${cancelling.title}」` });
      tasks.refresh();
      summary.refresh();
    }
    setCancelling(null);
    window.setTimeout(() => setFlash(null), 2500);
  }

  async function handleClaim(taskId: string, nodeId: string) {
    setBusy(true);
    const result = await apiClaimNode(taskId, nodeId);
    setBusy(false);
    if (!result.ok) {
      // 409 表示已被他人认领
      if (result.status === 409) {
        setFlash({ kind: "err", text: "该节点已被他人认领" });
      } else {
        setFlash({ kind: "err", text: result.error ?? "认领失败" });
      }
    } else {
      setFlash({ kind: "ok", text: "认领成功" });
      tasks.refresh();
      summary.refresh();
    }
    window.setTimeout(() => setFlash(null), 2500);
  }

  const columns = [
    {
      key: "title",
      header: "标题",
      render: (row: typeof tasks.items[number]) => (
        <button
          type="button"
          className="text-left text-frost hover:text-mint"
          onClick={() => navigate(`/console/tasks/${row.taskId}`)}
        >
          {row.title}
        </button>
      ),
    },
    {
      key: "state",
      header: "状态",
      render: (row: typeof tasks.items[number]) => (
        <ConsoleTag tone={stateTone(row.state)}>{stateLabel(row.state)}</ConsoleTag>
      ),
    },
    {
      key: "progress",
      header: "进度",
      render: (row: typeof tasks.items[number]) =>
        row.progressTotal > 0 ? `${row.progressDone}/${row.progressTotal}` : "—",
    },
    {
      key: "owner",
      header: "负责人",
      render: (row: typeof tasks.items[number]) => (
        <span className="font-mono text-[11px]">{row.ownerId || "—"}</span>
      ),
    },
    {
      key: "workflow",
      header: "流程",
      render: (row: typeof tasks.items[number]) =>
        row.workflowId ? (
          <span className="font-mono text-[11px] text-mute">
            {row.workflowId} v{row.workflowVersion ?? "-"}
          </span>
        ) : (
          <span className="text-mute">自由任务</span>
        ),
    },
    {
      key: "updated",
      header: "更新时间",
      render: (row: typeof tasks.items[number]) => (
        <span className="text-[11px] text-mute">{formatDateTime(row.updatedAt)}</span>
      ),
    },
    {
      key: "actions",
      header: "操作",
      render: (row: typeof tasks.items[number]) => (
        <span className="flex items-center gap-1.5">
          <button
            type="button"
            className="rounded border border-rail px-2 py-0.5 text-[11px] text-frost hover:text-mint"
            onClick={() => navigate(`/console/tasks/${row.taskId}`)}
          >
            详情
          </button>
          {row.claimable && can("task_create") && row.currentNode && (
            <button
              type="button"
              disabled={busy}
              className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
              onClick={() => void handleClaim(row.taskId, row.currentNode!)}
            >
              认领
            </button>
          )}
          {can("task_dispatch") && (
            <button
              type="button"
              disabled={busy}
              className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
              onClick={() => setCancelling({ taskId: row.taskId, title: row.title })}
            >
              取消
            </button>
          )}
        </span>
      ),
    },
  ];

  return (
    <>
      <ConsolePageHeader
        title="任务中心"
        description="创建、认领、推进与取消任务；按 Tab 切换全部 / 我的工作 / 审批"
        actions={can("task_create") ? (
          <button type="button" className="hud-btn text-xs" onClick={() => setCreateOpen(true)}>
            新建任务
          </button>
        ) : undefined}
      />

      <ConsoleTabs tabs={tabsWithBadges} value={tab} onChange={setTab} ariaLabel="任务页签" />

      {tab !== "mine" && tab !== "approvals" && (
        <div className="mb-4 flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            状态
            <select
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            >
              {STATE_OPTIONS.map((opt) => (
                <option key={opt.value || "all"} value={opt.value}>
                  {opt.label}
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
          <label className="text-[11px] text-mute">
            流程 ID
            <input
              className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={workflowFilter}
              onChange={(e) => setWorkflowFilter(e.target.value)}
              placeholder="workflow_id"
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs"
            onClick={() => tasks.refresh()}
          >
            刷新
          </button>
        </div>
      )}

      {flash?.kind === "err" && (
        <p className="mb-3 text-xs text-flare">{flash.text}</p>
      )}
      {flash?.kind === "ok" && (
        <p className="mb-3 text-xs text-mint">{flash.text}</p>
      )}

      {tab !== "approvals" && tasks.loading && tasks.items.length === 0 && (
        <ConsolePageState kind="loading" title="加载任务" description="获取列表中…" />
      )}

      {tab !== "approvals" && !tasks.loading && tasks.error && (
        <ConsolePageState
          kind="error"
          title="加载失败"
          description={tasks.error}
          action={
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => tasks.refresh()}
            >
              重试
            </button>
          }
        />
      )}

      {tab !== "approvals" && !tasks.loading && !tasks.error && (
        <ConsoleSection title={`任务（${tasks.items.length}/${tasks.total}）`}>
          <ConsoleTable
            rows={tasks.items}
            rowKey={(row) => row.taskId}
            loading={tasks.loading}
            empty={tab === "mine" ? "你目前没有打开的任务" : "暂无任务"}
            columns={columns}
          />
        </ConsoleSection>
      )}

      {tab === "approvals" && !canResolve && (
        <ConsolePageState kind="forbidden" title="无权处理审批" description="需要 hitl_resolve 权限。" />
      )}
      {tab === "approvals" && canResolve && (
        <ApprovalList
          rows={approvals.items}
          total={approvals.total}
          loading={approvals.loading}
          error={approvals.error}
          onRefresh={approvals.refresh}
          onOpen={(row) => navigate(`/console/tasks/${row.taskId}?approval_id=${encodeURIComponent(row.approvalId)}`)}
        />
      )}

      {createOpen && (
        <CreateTaskDialog
          canDispatch={can("task_dispatch")}
          onClose={() => setCreateOpen(false)}
          onCreated={(taskId) => {
            setCreateOpen(false);
            summary.refresh();
            navigate(`/console/tasks/${taskId}`);
          }}
        />
      )}

      <ConfirmDialog
        open={!!cancelling}
        title="取消任务"
        description={
          cancelling
            ? `确定要取消「${cancelling.title}」吗？任务状态将变为 cancelled，默认原因：manual。`
            : undefined
        }
        confirmLabel="确认取消"
        cancelLabel="返回"
        danger
        busy={busy}
        onCancel={() => setCancelling(null)}
        onConfirm={() => void handleCancelReasoned("manual")}
      />
    </>
  );
}

function CreateTaskDialog({
  canDispatch,
  onClose,
  onCreated,
}: {
  canDispatch: boolean;
  onClose: () => void;
  onCreated: (taskId: string) => void;
}) {
  const workflows = useWorkflows({ limit: 100, offset: 0 });
  const published = workflows.items.filter((workflow) => workflow.publishedVersion != null);
  const [title, setTitle] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (!title.trim()) {
      setError("任务标题不能为空");
      return;
    }
    setBusy(true);
    setError("");
    const result = await createTask({
      title: title.trim(),
      workflow_id: workflowId || null,
      owner_id: canDispatch ? ownerId.trim() || null : null,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onCreated(result.data.task_id);
  }

  return (
    <Dialog
      open
      title="新建并启动任务"
      description="创建成功后任务立即启动，并进入任务详情。"
      onClose={() => { if (!busy) onClose(); }}
      footer={
        <>
          <button type="button" className="rounded border border-rail px-3 py-1.5 text-xs text-mute" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button type="button" className="hud-btn text-xs disabled:opacity-40" disabled={busy} onClick={() => void submit()}>
            {busy ? "创建中…" : "创建并启动"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block text-[11px] text-mute">
          任务标题
          <input
            autoFocus
            className="mt-1 block w-full rounded border border-rail bg-abyss px-2 py-1.5 text-xs text-frost"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="block text-[11px] text-mute">
          任务类型
          <select
            className="mt-1 block w-full rounded border border-rail bg-abyss px-2 py-1.5 text-xs text-frost"
            value={workflowId}
            onChange={(event) => setWorkflowId(event.target.value)}
          >
            <option value="">自由任务</option>
            {published.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name} · v{workflow.publishedVersion}
              </option>
            ))}
          </select>
          {workflows.loading && <span className="mt-1 block">正在加载已发布工作流…</span>}
          {workflows.error && <span className="mt-1 block text-flare">{workflows.error}</span>}
        </label>
        {canDispatch && (
          <label className="block text-[11px] text-mute">
            指定负责人（可选）
            <input
              className="mt-1 block w-full rounded border border-rail bg-abyss px-2 py-1.5 font-mono text-xs text-frost"
              placeholder="留空由当前用户创建"
              value={ownerId}
              onChange={(event) => setOwnerId(event.target.value)}
            />
          </label>
        )}
        {error && <p role="alert" className="text-xs text-flare">{error}</p>}
      </div>
    </Dialog>
  );
}

function ApprovalList({
  rows,
  total,
  loading,
  error,
  onRefresh,
  onOpen,
}: {
  rows: ApprovalRow[];
  total: number;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onOpen: (row: ApprovalRow) => void;
}) {
  if (loading && rows.length === 0) return <ConsolePageState kind="loading" title="加载审批" />;
  if (error) {
    return <ConsolePageState kind="error" title="审批加载失败" description={error} action={<button type="button" className="hud-btn text-xs" onClick={onRefresh}>重试</button>} />;
  }
  return (
    <ConsoleSection
      title={`待处理审批（${rows.length}/${total}）`}
      actions={<button type="button" className="rounded border border-rail px-2 py-1 text-xs text-mute" onClick={onRefresh}>刷新</button>}
    >
      <ConsoleTable
        rows={rows}
        rowKey={(row) => row.approvalId}
        loading={loading}
        empty="当前没有待处理的审批"
        columns={[
          {
            key: "title",
            header: "标题",
            render: (row) => <button type="button" className="text-left text-frost hover:text-mint" onClick={() => onOpen(row)}>{row.title}</button>,
          },
          { key: "tier", header: "类型", render: (row) => <ConsoleTag>{row.tier}</ConsoleTag> },
          { key: "requester", header: "发起人", render: (row) => <span className="font-mono text-[11px]">{row.requesterId ?? "—"}</span> },
          { key: "waiting", header: "等待时长", render: (row) => waitingText(row.createdAt) },
          { key: "status", header: "状态", render: (row) => <ConsoleTag tone="warn">{row.status}</ConsoleTag> },
          { key: "action", header: "操作", render: (row) => <button type="button" className="hud-btn px-2 py-0.5 text-[11px]" onClick={() => onOpen(row)}>处理</button> },
        ]}
      />
    </ConsoleSection>
  );
}

function waitingText(createdAt: string | null): string {
  if (!createdAt) return "—";
  const created = new Date(createdAt).getTime();
  if (Number.isNaN(created)) return "—";
  const minutes = Math.max(0, Math.floor((Date.now() - created) / 60_000));
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时`;
  return `${Math.floor(hours / 24)} 天`;
}
