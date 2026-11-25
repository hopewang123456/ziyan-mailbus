import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { ConsolePageState } from "../../components/console/ConsolePageState";
import { ConsoleTabs, useTabParam } from "../../components/console/ConsoleTabs";
import { ConfirmDialog, Dialog } from "../../components/console/ConsoleDialog";
import { useTask, useTaskTrace, useApproval } from "../../lib/task/hooks";
import {
  cancelTask as apiCancelTask,
  claimNode as apiClaimNode,
  submitResult as apiSubmitResult,
  resolveApproval,
  rerunJoin as apiRerunJoin,
  uploadArtifact as apiUploadArtifact,
  getArtifact,
} from "../../lib/task/api";
import { stateTone, stateLabel } from "../../lib/task/view";
import { formatDateTime, formatBytes } from "../../lib/format";
import { useConsoleAccess } from "../../lib/console-access";
import type { ApprovalRow, ArtifactRow, TaskDetailRow } from "../../lib/task/view";

const TABS = ["overview", "trace", "variables", "artifacts"] as const;
type TabKey = (typeof TABS)[number];

const RUN_STATE_TONE: Record<string, "ok" | "warn" | "danger" | "default"> = {
  queued: "warn",
  running: "ok",
  waiting: "warn",
  approval: "warn",
  blocked: "warn",
  done: "ok",
  success: "ok",
  failed: "danger",
  error: "danger",
  cancelled: "default",
  skipped: "default",
};

function runStateTone(state: string) {
  return RUN_STATE_TONE[state] ?? "default";
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  const rem = ms % 1000;
  if (s < 60) return rem > 0 ? `${s}.${String(rem).padStart(3, "0").slice(0, 1)}s` : `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m}m ${rs}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

export function ConsoleTaskDetailPage({
  can,
}: {
  can: (capability: string) => boolean;
}) {
  const navigate = useNavigate();
  const access = useConsoleAccess();
  const [searchParams] = useSearchParams();
  const { task_id } = useParams();
  const taskId = task_id ?? "";

  const [tab, setTab] = useTabParam<TabKey>(TABS, "overview");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [resultTarget, setResultTarget] = useState<{ nodeId: string; attemptNo: number } | null>(null);
  const [rerunning, setRerunning] = useState<{ nodeId: string; fanoutGroup: string } | null>(null);

  const detail = useTask(taskId || null);
  const trace = useTaskTrace(taskId || null);
  const approvalId = searchParams.get("approval_id");
  const approval = useApproval(approvalId);

  const task = detail.data;

  const currentNodeId = useMemo(() => {
    if (!task) return null;
    const runningNode = task.nodes.find(
      (n) => n.state === "running" || n.state === "queued" || n.state === "approval" || n.state === "waiting",
    );
    if (runningNode) return runningNode.nodeId;
    const doneNode = task.nodes.find((n) => n.state !== "done" && n.state !== "cancelled" && n.state !== "skipped");
    return doneNode?.nodeId ?? null;
  }, [task]);

  function flashMessage(kind: "ok" | "err", text: string) {
    setFlash({ kind, text });
    window.setTimeout(() => setFlash(null), 2500);
  }

  async function handleCancel() {
    setCancelling(false);
    setBusy(true);
    const result = await apiCancelTask(taskId, { reason: "manual" });
    setBusy(false);
    if (!result.ok) {
      flashMessage("err", result.error ?? "取消失败");
    } else {
      flashMessage("ok", "任务已取消");
      detail.refresh();
    }
  }

  async function handleClaim() {
    if (!currentNodeId) return;
    setBusy(true);
    const result = await apiClaimNode(taskId, currentNodeId);
    setBusy(false);
    if (!result.ok) {
      if (result.status === 409) {
        flashMessage("err", "该节点已被他人认领");
      } else {
        flashMessage("err", result.error ?? "认领失败");
      }
    } else {
      flashMessage("ok", "认领成功");
      detail.refresh();
    }
  }

  async function handleSubmitResult(value: string, artifactIds: string[]): Promise<string | null> {
    if (!resultTarget) return "提交目标已失效，请刷新后重试";
    setBusy(true);
    const result = await apiSubmitResult(taskId, resultTarget.nodeId, {
      attempt_no: resultTarget.attemptNo,
      result: value,
      ...(artifactIds.length > 0 ? { artifact_ids: artifactIds } : {}),
    });
    setBusy(false);
    if (!result.ok) {
      if (result.status === 409) {
        detail.refresh();
        return "该节点已被重新指派，请刷新后重试";
      }
      return result.error;
    }
    setResultTarget(null);
    flashMessage("ok", "结果已提交");
    detail.refresh();
    return null;
  }

  async function handleRerunJoin(nodeId: string, fanoutGroup: string) {
    setRerunning(null);
    setBusy(true);
    const result = await apiRerunJoin(taskId, nodeId, {
      fanout_group: fanoutGroup,
      scope: "join",
    });
    setBusy(false);
    if (!result.ok) {
      flashMessage("err", result.error ?? "rerun-join 失败");
    } else {
      flashMessage("ok", "已触发 rerun-join");
      detail.refresh();
    }
  }

  if (!taskId) {
    return <ConsolePageState kind="not-found" title="任务 ID 缺失" />;
  }

  if (detail.loading && !task) {
    return <ConsolePageState kind="loading" title="加载任务详情" />;
  }

  if (detail.error && !task) {
    return (
      <ConsolePageState
        kind="error"
        title="加载失败"
        description={detail.error}
        action={
          <button type="button" className="hud-btn text-xs" onClick={() => navigate("/console/tasks")}>
            返回任务列表
          </button>
        }
      />
    );
  }

  if (!task) return null;

  return (
    <>
      <ConsolePageHeader
        title={task.title}
        description={task.taskId}
        actions={
          <>
            <Link to="/console/tasks" className="hud-btn text-xs">
              ← 任务列表
            </Link>
            {can("task_dispatch") && (
              <button
                type="button"
                disabled={busy}
                className="rounded border border-flare/50 px-3 py-1 text-xs text-flare hover:bg-flare/10 disabled:opacity-40"
                onClick={() => setCancelling(true)}
              >
                取消任务
              </button>
            )}
          </>
        }
      />

      {flash?.kind === "err" && (
        <p className="mb-3 text-xs text-flare">{flash.text}</p>
      )}
      {flash?.kind === "ok" && (
        <p className="mb-3 text-xs text-mint">{flash.text}</p>
      )}

      {approvalId && (
        <ApprovalActionCard
          approval={approval.data}
          loading={approval.loading}
          error={approval.error}
          canResolve={can("hitl_resolve")}
          onResolved={() => {
            approval.refresh();
            detail.refresh();
            flashMessage("ok", "审批已处理");
          }}
        />
      )}

      <section className="mb-5 rounded-lg border border-rail bg-hull/40 p-4">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] md:grid-cols-4">
          <div>
            <dt className="text-mute">状态</dt>
            <dd>
              <ConsoleTag tone={stateTone(task.state)}>{stateLabel(task.state)}</ConsoleTag>
            </dd>
          </div>
          <div>
            <dt className="text-mute">负责人</dt>
            <dd className="font-mono">{task.ownerId || "—"}</dd>
          </div>
          <div>
            <dt className="text-mute">流程</dt>
            <dd className="font-mono">
              {task.workflowId
                ? `${task.workflowId} v${task.workflowVersion ?? "-"}`
                : "自由任务"}
            </dd>
          </div>
          <div>
            <dt className="text-mute">创建人</dt>
            <dd className="font-mono">{task.createdBy || "—"}</dd>
          </div>
          <div>
            <dt className="text-mute">创建时间</dt>
            <dd>{formatDateTime(task.createdAt)}</dd>
          </div>
          <div>
            <dt className="text-mute">更新时间</dt>
            <dd>{formatDateTime(task.updatedAt)}</dd>
          </div>
          {task.terminationReason && (
            <div className="col-span-2">
              <dt className="text-mute">终止原因</dt>
              <dd>{task.terminationReason}</dd>
            </div>
          )}
        </dl>
      </section>

      <ConsoleTabs tabs={TABS.map((k) => ({ key: k, label: TAB_LABEL[k] }))} value={tab} onChange={setTab} ariaLabel="任务详情页签" />

      {tab === "overview" && <OverviewTab task={task} can={can} busy={busy}
        employeeId={access.employeeId}
        onClaim={handleClaim}
        onSubmitResult={(nodeId, attemptNo) => setResultTarget({ nodeId, attemptNo })}
        onRequestRerunJoin={(nodeId, fanoutGroup) => setRerunning({ nodeId, fanoutGroup })}
      />}

      {tab === "trace" && <TraceTab events={trace.events} loading={trace.loading} error={trace.error} />}

      {tab === "variables" && <VariablesTab task={task} />}

      {tab === "artifacts" && (
        <ArtifactsTab
          task={task}
          can={can}
          defaultNodeId={currentNodeId}
          onUploaded={() => detail.refresh()}
        />
      )}

      {resultTarget && (
        <ResultSubmitDialog
          target={resultTarget}
          busy={busy}
          artifacts={task.artifacts.filter((a) => a.nodeId === resultTarget.nodeId)}
          onClose={() => { if (!busy) setResultTarget(null); }}
          onSubmit={handleSubmitResult}
        />
      )}

      <ConfirmDialog
        open={cancelling}
        title="取消任务"
        description="默认 reason: manual。取消后任务状态变为 cancelled，不可恢复。"
        confirmLabel="确认取消"
        cancelLabel="返回"
        danger
        busy={busy}
        onCancel={() => setCancelling(false)}
        onConfirm={() => void handleCancel()}
      />

      <ConfirmDialog
        open={!!rerunning}
        title="Rerun-Join"
        description={
          rerunning
            ? `对节点 ${rerunning.nodeId}（fanout_group: ${rerunning.fanoutGroup || "-"}）执行 rerun-join，默认 scope=join（只重跑缺失节点）。`
            : undefined
        }
        confirmLabel="执行"
        cancelLabel="返回"
        busy={busy}
        onCancel={() => setRerunning(null)}
        onConfirm={() => rerunning && void handleRerunJoin(rerunning.nodeId, rerunning.fanoutGroup)}
      />
    </>
  );
}

function ResultSubmitDialog({
  target,
  busy,
  artifacts,
  onClose,
  onSubmit,
}: {
  target: { nodeId: string; attemptNo: number };
  busy: boolean;
  artifacts: ArtifactRow[];
  onClose: () => void;
  onSubmit: (value: string, artifactIds: string[]) => Promise<string | null>;
}) {
  const [mode, setMode] = useState<"markdown" | "json">("markdown");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  function toggleArtifact(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setError("");
  }

  async function submit() {
    const result = value.trim();
    if (!result) {
      setError("结果内容不能为空");
      return;
    }
    if (mode === "json") {
      try {
        JSON.parse(result);
      } catch {
        setError("JSON 格式不正确，请修正后再提交");
        return;
      }
    }
    setError("");
    const submitError = await onSubmit(result, Array.from(selected));
    if (submitError) setError(submitError);
  }

  return (
    <Dialog
      open
      width={640}
      title="提交节点结果"
      description={`节点 ${target.nodeId} · attempt #${target.attemptNo}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="rounded border border-rail px-3 py-1.5 text-xs text-mute" disabled={busy} onClick={onClose}>取消</button>
          <button type="button" className="hud-btn text-xs disabled:opacity-40" disabled={busy} onClick={() => void submit()}>
            {busy ? "提交中…" : "提交结果"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex gap-2" aria-label="结果格式">
          {(["markdown", "json"] as const).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              className={`rounded border px-3 py-1 text-xs ${mode === key ? "border-mint text-mint" : "border-rail text-mute"}`}
              disabled={busy}
              onClick={() => { setMode(key); setError(""); }}
            >
              {key === "markdown" ? "Markdown" : "JSON"}
            </button>
          ))}
        </div>
        <textarea
          autoFocus
          rows={9}
          className="w-full rounded border border-rail bg-abyss p-3 font-mono text-xs text-frost"
          placeholder={mode === "json" ? '{"summary":"..."}' : "输入 Markdown 结果"}
          value={value}
          onChange={(event) => { setValue(event.target.value); setError(""); }}
        />
        {artifacts.length > 0 ? (
          <div className="rounded border border-rail bg-hull/40 px-3 py-2">
            <p className="mb-1 text-[11px] text-mute">挂载本节点产物（可选）：</p>
            <div className="flex flex-col gap-1">
              {artifacts.map((a) => (
                <label key={a.artifactId} className="flex items-center gap-2 text-[11px] text-frost">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5"
                    checked={selected.has(a.artifactId)}
                    disabled={busy}
                    onChange={() => toggleArtifact(a.artifactId)}
                  />
                  <span className="font-mono">{a.fileName}</span>
                  <span className="text-mute">{formatBytes(a.sizeBytes)}</span>
                </label>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded border border-rail bg-hull/40 px-3 py-2 text-[11px] text-mute">
            本节点暂无已上传产物。可先在「产物」页签上传本节点产物，再回到此处挂载。
          </p>
        )}
        {error && <p role="alert" className="text-xs text-flare">{error}</p>}
      </div>
    </Dialog>
  );
}

function ApprovalActionCard({
  approval,
  loading,
  error,
  canResolve,
  onResolved,
}: {
  approval: ApprovalRow | null;
  loading: boolean;
  error: string | null;
  canResolve: boolean;
  onResolved: () => void;
}) {
  const [decision, setDecision] = useState<"approved" | "rejected" | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [resolveError, setResolveError] = useState("");

  async function resolve() {
    if (!approval || !decision) return;
    if (decision === "rejected" && !comment.trim()) {
      setResolveError("驳回审批时必须填写意见");
      return;
    }
    setBusy(true);
    setResolveError("");
    const result = await resolveApproval(approval.approvalId, {
      decision,
      comment: comment.trim() || null,
    });
    setBusy(false);
    if (!result.ok) {
      setResolveError(result.error);
      return;
    }
    setDecision(null);
    setComment("");
    onResolved();
  }

  return (
    <ConsoleSection title="审批处理">
      {loading && !approval && <p className="text-xs text-mute">正在加载审批…</p>}
      {error && <p className="text-xs text-flare">{error}</p>}
      {approval && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-frost">{approval.title}</p>
            <ConsoleTag>{approval.tier}</ConsoleTag>
            <ConsoleTag tone={approval.status === "pending" ? "warn" : approval.status === "approved" ? "ok" : "danger"}>
              {approval.status}
            </ConsoleTag>
          </div>
          <dl className="grid gap-2 text-[11px] sm:grid-cols-3">
            <div><dt className="text-mute">发起人</dt><dd className="font-mono">{approval.requesterId ?? "—"}</dd></div>
            <div><dt className="text-mute">节点</dt><dd className="font-mono">{approval.nodeId ?? "—"}</dd></div>
            <div><dt className="text-mute">发起时间</dt><dd>{formatDateTime(approval.createdAt)}</dd></div>
          </dl>
          {approval.note && <pre className="whitespace-pre-wrap rounded border border-rail bg-hull/40 p-3 text-xs text-frost">{approval.note}</pre>}
          {approval.resolutionNote && <p className="text-xs text-mute">处理意见：{approval.resolutionNote}</p>}
          {approval.status === "pending" && canResolve && (
            <>
              <p className="text-[11px] text-mute">或签：任一人处理即生效，其余待办自动关闭。</p>
              <div className="flex gap-2">
                <button type="button" className="hud-btn text-xs" onClick={() => { setDecision("approved"); setResolveError(""); }}>通过</button>
                <button type="button" className="rounded border border-flare/50 px-3 py-1 text-xs text-flare" onClick={() => { setDecision("rejected"); setResolveError(""); }}>驳回</button>
              </div>
            </>
          )}
        </div>
      )}
      <Dialog
        open={decision !== null}
        title={decision === "approved" ? "通过审批" : "驳回审批"}
        description={decision === "rejected" ? "驳回意见必填。" : "处理意见可选。"}
        onClose={() => { if (!busy) setDecision(null); }}
        footer={
          <>
            <button type="button" className="rounded border border-rail px-3 py-1.5 text-xs text-mute" disabled={busy} onClick={() => setDecision(null)}>取消</button>
            <button type="button" className="hud-btn text-xs disabled:opacity-40" disabled={busy} onClick={() => void resolve()}>
              {busy ? "处理中…" : decision === "approved" ? "确认通过" : "确认驳回"}
            </button>
          </>
        }
      >
        <textarea
          autoFocus
          rows={5}
          className="w-full rounded border border-rail bg-abyss p-2 text-xs text-frost"
          placeholder="处理意见"
          value={comment}
          onChange={(event) => { setComment(event.target.value); setResolveError(""); }}
        />
        {resolveError && <p role="alert" className="mt-2 text-xs text-flare">{resolveError}</p>}
      </Dialog>
    </ConsoleSection>
  );
}

const TAB_LABEL: Record<TabKey, string> = {
  overview: "概览",
  trace: "时间线",
  variables: "变量",
  artifacts: "产物",
};

/* ---------- Tab 内容 ---------- */

function OverviewTab({
  task,
  can,
  busy,
  employeeId,
  onClaim,
  onSubmitResult,
  onRequestRerunJoin,
}: {
  task: ReturnType<typeof mapTaskDetailLocal>;
  can: (c: string) => boolean;
  busy: boolean;
  employeeId?: string;
  onClaim: () => void;
  onSubmitResult: (nodeId: string, attemptNo: number) => void;
  onRequestRerunJoin: (nodeId: string, fanoutGroup: string) => void;
}) {
  /** 取每个 node 的当前 run（attempt_no 最大） */
  const latestRunByNode = useMemo(() => {
    const map = new Map<string, typeof task.runs[number]>();
    for (const run of task.runs) {
      const existing = map.get(run.nodeId);
      if (!existing || run.attemptNo > existing.attemptNo) {
        map.set(run.nodeId, run);
      }
    }
    return map;
  }, [task.runs]);

  return (
    <>
      {can("task_create") && (
        <ConsoleSection title="认领与结果提交">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              className="hud-btn text-xs disabled:opacity-40"
              onClick={() => void onClaim()}
            >
              认领当前节点
            </button>
            <span className="text-[11px] text-mute">
              只能认领处于 running/queued/waiting/approval 状态的节点；409 表示已被他人认领。
            </span>
          </div>
        </ConsoleSection>
      )}

      {task.nodes.length > 0 ? (
        <ConsoleSection title={`节点（${task.nodes.length}）`}>
          <ConsoleTable
            rows={task.nodes}
            rowKey={(n) => n.nodeId}
            empty="此任务没有节点（自由任务）"
            columns={[
              { key: "seq", header: "#", render: (n) => String(n.seq) },
              { key: "name", header: "节点", render: (n) => n.name },
              { key: "state", header: "状态", render: (n) => <ConsoleTag tone={runStateTone(n.state)}>{stateLabel(n.state)}</ConsoleTag> },
              {
                key: "current_run",
                header: "当前 Attempt",
                render: (n) => {
                  const run = latestRunByNode.get(n.nodeId);
                  return run ? `#${run.attemptNo}` : "—";
                },
              },
              {
                key: "actions",
                header: "操作",
                render: (n) => {
                  const run = latestRunByNode.get(n.nodeId);
                  return (
                    <span className="flex gap-1.5">
                      {can("result_submit") && run?.state === "running" && run.assignedEmployeeId === employeeId && (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
                          onClick={() => onSubmitResult(n.nodeId, run.attemptNo)}
                        >
                          提交结果
                        </button>
                      )}
                      {can("result_submit") && run?.fanoutGroup && (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-rail px-2 py-0.5 text-[11px] text-frost hover:text-mint disabled:opacity-40"
                          onClick={() => run && onRequestRerunJoin(n.nodeId, run.fanoutGroup!)}
                        >
                          rerun-join
                        </button>
                      )}
                    </span>
                  );
                },
              },
            ]}
          />
        </ConsoleSection>
      ) : null}

      {task.runs.length > 0 ? (
        <ConsoleSection title={`节点 Run（${task.runs.length}）`}>
          <ConsoleTable
            rows={task.runs}
            rowKey={(r) => r.runId}
            columns={[
              { key: "node", header: "节点", render: (r) => <span className="font-mono text-[11px]">{r.nodeId}</span> },
              { key: "attempt", header: "#", render: (r) => `#${r.attemptNo}` },
              { key: "state", header: "状态", render: (r) => <ConsoleTag tone={runStateTone(r.state)}>{stateLabel(r.state)}</ConsoleTag> },
              { key: "assigned", header: "负责人", render: (r) => <span className="font-mono text-[11px]">{r.assignedEmployeeId || "—"}</span> },
              { key: "fanout", header: "Fanout", render: (r) => r.fanoutGroup ? <span className="font-mono text-[11px]">{r.fanoutGroup}#{r.fanoutSlot}</span> : "—" },
              { key: "started", header: "开始", render: (r) => <span className="text-[11px] text-mute">{formatDateTime(r.startedAt)}</span> },
              { key: "finished", header: "结束", render: (r) => <span className="text-[11px] text-mute">{formatDateTime(r.completedAt)}</span> },
              { key: "duration", header: "耗时", render: (r) => formatDuration(r.durationMs) },
              { key: "result", header: "结果", render: (r) => r.result ? <span className="font-mono text-[11px]">{r.result}</span> : "—" },
            ]}
          />
        </ConsoleSection>
      ) : null}
    </>
  );
}

/** 把页面 import 用 `TaskDetailRow` 引用的地方走这个别名（避免 view.ts 的循环引用字面量）。 */
function mapTaskDetailLocal(_t: unknown) {
  return _t as {
    runs: ReturnType<typeof import("../../lib/task/view").mapRun>[];
    nodes: ReturnType<typeof import("../../lib/task/view").mapNode>[];
  };
}

function TraceTab({ events, loading, error }: { events: ReturnType<typeof import("../../lib/task/view").mapTraceEvent>[]; loading: boolean; error: string | null }) {
  if (loading) return <ConsolePageState kind="loading" title="加载时间线" />;
  if (error) return <ConsolePageState kind="error" title="时间线加载失败" description={error} />;
  if (events.length === 0) return <ConsolePageState kind="empty" title="尚无事件" />;

  return (
    <ConsoleSection title={`事件（${events.length}）`}>
      <ol className="relative ml-3 border-l border-rail pl-4">
        {events.map((e, i) => (
          <li key={`${e.runId || "t"}-${i}`} className="mb-3 last:mb-0">
            <div className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full bg-mint" />
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="font-mono text-mute">{formatDateTime(e.at)}</span>
              <ConsoleTag tone="default">{e.kind}</ConsoleTag>
              {e.nodeId && <span className="font-mono text-mute">node={e.nodeId}</span>}
              {e.runId && <span className="font-mono text-mute">run={e.runId}</span>}
              {typeof e.attemptNo === "number" && <span className="font-mono text-mute">#{e.attemptNo}</span>}
            </div>
            {e.detail && Object.keys(e.detail).length > 0 && (
              <pre className="mt-1 overflow-x-auto rounded bg-abyss/40 p-2 font-mono text-[10px] text-mute">
                {JSON.stringify(e.detail, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ol>
    </ConsoleSection>
  );
}

function VariablesTab({ task }: { task: { taskId: string; workflowId: string | null } }) {
  // 契约 TaskDetailOut 没有 task_context/run_context 字段。此 Tab 展示占位，避免瞎填假数据。
  return (
    <ConsoleSection title="变量">
      <div className="rounded-lg border border-dashed border-rail px-6 py-8 text-center">
        <p className="text-sm text-frost">本版本契约未暴露 task_context / run_context 字段。</p>
        <p className="mt-1 text-xs text-mute">待后端在 TaskDetailOut 或独立 endpoint 返回后再接入。</p>
        <p className="mt-4 text-[11px] text-mute">
          task_id: <span className="font-mono">{task.taskId}</span>
          {task.workflowId && <> · workflow_id: <span className="font-mono">{task.workflowId}</span></>}
        </p>
      </div>
    </ConsoleSection>
  );
}

function ArtifactsTab({
  task,
  can,
  defaultNodeId,
  onUploaded,
}: {
  task: TaskDetailRow;
  can: (capability: string) => boolean;
  defaultNodeId: string | null;
  onUploaded: () => void;
}) {
  const canUpload = can("result_submit");
  const [nodeId, setNodeId] = useState<string>(defaultNodeId ?? task.nodes[0]?.nodeId ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  async function handleUpload() {
    if (!nodeId || !file) return;
    setUploading(true);
    setMsg(null);
    const result = await apiUploadArtifact(task.taskId, nodeId, file, description.trim() || null);
    setUploading(false);
    if (!result.ok) {
      setMsg({ kind: "err", text: result.error ?? "上传失败" });
      return;
    }
    setMsg({ kind: "ok", text: `已上传 ${result.data.file_name}` });
    setFile(null);
    setDescription("");
    onUploaded();
  }

  async function handleDownload(a: ArtifactRow) {
    setDownloadingId(a.artifactId);
    setMsg(null);
    const result = await getArtifact(a.artifactId, { filename: a.fileName });
    setDownloadingId(null);
    if (!result.ok) {
      setMsg({ kind: "err", text: result.error ?? "下载失败" });
    }
  }

  return (
    <ConsoleSection title={`产物（${task.artifacts.length}）`}>
      {canUpload && (
        <div className="mb-4 rounded border border-rail bg-hull/40 p-3">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-[11px] text-mute">节点</label>
              <select
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
                disabled={uploading}
                className="rounded border border-rail bg-abyss px-2 py-1.5 text-xs text-frost"
              >
                {task.nodes.map((n) => (
                  <option key={n.nodeId} value={n.nodeId}>
                    {n.name} ({n.nodeId})
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-[11px] text-mute">文件（≤100MB）</label>
              <input
                type="file"
                disabled={uploading}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-frost file:mr-2 file:rounded file:border-0 file:bg-mint/20 file:px-2 file:py-1 file:text-xs file:text-mint"
              />
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-[11px] text-mute">描述（可选）</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={uploading}
                placeholder="产物说明"
                className="w-full rounded border border-rail bg-abyss px-2 py-1.5 text-xs text-frost"
              />
            </div>
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={uploading || !nodeId || !file}
              onClick={() => void handleUpload()}
            >
              {uploading ? "上传中…" : "上传产物"}
            </button>
          </div>
        </div>
      )}
      {msg && (
        <p className={`mb-3 text-xs ${msg.kind === "ok" ? "text-mint" : "text-flare"}`}>{msg.text}</p>
      )}
      {task.artifacts.length === 0 ? (
        <p className="text-xs text-mute">暂无产物。</p>
      ) : (
        <ConsoleTable
          rows={task.artifacts}
          rowKey={(a) => a.artifactId}
          columns={[
            {
              key: "name",
              header: "文件",
              render: (a) => (
                <button
                  type="button"
                  className="font-mono text-[11px] text-mint hover:underline disabled:opacity-40"
                  disabled={downloadingId === a.artifactId}
                  onClick={() => void handleDownload(a)}
                >
                  {downloadingId === a.artifactId ? "下载中…" : a.fileName}
                </button>
              ),
            },
            { key: "node", header: "节点", render: (a) => <span className="font-mono text-[11px]">{a.nodeId ?? "—"}</span> },
            { key: "size", header: "大小", render: (a) => formatBytes(a.sizeBytes) },
            { key: "desc", header: "描述", render: (a) => a.description ? <span className="text-[11px] text-frost">{a.description}</span> : "—" },
            { key: "by", header: "上传人", render: (a) => <span className="font-mono text-[11px]">{a.createdBy ?? "—"}</span> },
            { key: "at", header: "时间", render: (a) => <span className="text-[11px] text-mute">{formatDateTime(a.createdAt)}</span> },
          ]}
        />
      )}
    </ConsoleSection>
  );
}
