import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 审批中心：HITL 请求列表与裁决；阻塞档裁决会同步推进任务状态。 */

type Approval = {
  approval_id: string;
  task_id: string;
  node_id?: string | null;
  title: string;
  tier: string;
  status: string;
  requester_id?: string | null;
  note?: string | null;
  created_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
};

type Tab = "pending" | "approved" | "rejected" | "all";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "pending", label: "待裁决" },
  { key: "approved", label: "已通过" },
  { key: "rejected", label: "已拒绝" },
  { key: "all", label: "全部" },
];

const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "default"> = {
  pending: "warn",
  approved: "ok",
  acknowledged: "ok",
  rejected: "danger",
  expired: "danger",
};

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleApprovalsPage({ can }: { can: (capability: string) => boolean }) {
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<Approval[]>([]);
  const [tasks, setTasks] = useState<Array<{ task_id: string; title: string; state: string }>>([]);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    task_id: "",
    title: "",
    tier: "advisory",
    node_id: "",
    timeout_minutes: "",
    note: "",
  });

  const canCreate = can("hitl_request") || can("console_admin");

  const load = async (status: Tab) => {
    setLoading(true);
    const query = status === "all" ? "" : `?status=${status}`;
    const result = await api<Approval[]>(`/api/approvals${query}`);
    setLoading(false);
    if (result.ok) {
      setRows(result.data);
      setErr("");
    } else {
      setRows([]);
      setErr(result.error);
    }
  };

  useEffect(() => {
    void load(tab);
  }, [tab]);

  useEffect(() => {
    void api<Array<{ task_id: string; title: string; state: string }>>("/api/tasks").then(
      (result) => {
        if (result.ok && Array.isArray(result.data)) setTasks(result.data);
      },
    );
  }, []);

  async function createApproval() {
    setErr("");
    setMsg("");
    if (!form.task_id.trim() || !form.title.trim()) {
      setErr("任务 ID 与标题必填");
      return;
    }
    const timeout = Number(form.timeout_minutes);
    const result = await api<Approval>("/api/approvals", {
      method: "POST",
      body: JSON.stringify({
        task_id: form.task_id.trim(),
        title: form.title.trim(),
        tier: form.tier,
        node_id: form.node_id.trim() || null,
        timeout_minutes: Number.isInteger(timeout) && timeout > 0 ? timeout : null,
        note: form.note.trim() || null,
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已发起「${result.data.title}」（${result.data.tier}）`);
    setForm({ task_id: "", title: "", tier: "advisory", node_id: "", timeout_minutes: "", note: "" });
    setShowCreate(false);
    if (tab !== "pending" && tab !== "all") setTab("pending");
    else await load(tab);
  }

  async function resolve(row: Approval, approved: boolean) {
    setErr("");
    setMsg("");
    const result = await api(
      `/api/approvals/${encodeURIComponent(row.approval_id)}/resolve`,
      {
        method: "POST",
        body: JSON.stringify({ approved, note: note.trim() || null }),
      },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`${approved ? "已通过" : "已拒绝"}「${row.title}」`);
    setNote("");
    await load(tab);
  }

  return (
    <>
      <ConsolePageHeader
        title="审批中心"
        description="阻塞档审批会改变任务状态；裁决前可填写备注"
        actions={
          canCreate ? (
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => setShowCreate((value) => !value)}
            >
              {showCreate ? "收起" : "发起审批"}
            </button>
          ) : undefined
        }
      />

      {showCreate && canCreate && (
        <ConsoleSection title="发起审批">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-mute">
              任务 ID
              <input
                list="approval-task-options"
                className="mt-1 block w-44 rounded border border-rail bg-hull px-2 py-1.5 font-mono text-xs text-frost"
                value={form.task_id}
                maxLength={128}
                placeholder="task_..."
                onChange={(e) => setForm({ ...form, task_id: e.target.value })}
              />
              <datalist id="approval-task-options">
                {tasks.map((task) => (
                  <option key={task.task_id} value={task.task_id}>
                    {task.title} · {task.state}
                  </option>
                ))}
              </datalist>
            </label>
            <label className="text-[11px] text-mute">
              标题
              <input
                className="mt-1 block w-48 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={form.title}
                maxLength={64}
                placeholder="例如 发布前人工确认"
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label className="text-[11px] text-mute">
              档位
              <select
                className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={form.tier}
                onChange={(e) => setForm({ ...form, tier: e.target.value })}
              >
                <option value="blocking">blocking · 阻塞</option>
                <option value="advisory">advisory · 建议</option>
                <option value="informational">informational · 通知</option>
              </select>
            </label>
            <label className="text-[11px] text-mute">
              节点 ID（可选）
              <input
                className="mt-1 block w-32 rounded border border-rail bg-hull px-2 py-1.5 font-mono text-xs text-frost"
                value={form.node_id}
                maxLength={128}
                onChange={(e) => setForm({ ...form, node_id: e.target.value })}
              />
            </label>
            <label className="text-[11px] text-mute">
              超时分钟（可选）
              <input
                type="number"
                min={1}
                className="mt-1 block w-24 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={form.timeout_minutes}
                onChange={(e) => setForm({ ...form, timeout_minutes: e.target.value })}
              />
            </label>
            <label className="flex-1 text-[11px] text-mute">
              备注
              <input
                className="mt-1 block w-full min-w-40 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                value={form.note}
                maxLength={256}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </label>
            <button type="button" className="hud-btn text-xs" onClick={() => void createApproval()}>
              提交审批
            </button>
          </div>
        </ConsoleSection>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`rounded border px-2.5 py-1 text-xs ${
              tab === item.key
                ? "border-mint/50 bg-mint/10 text-mint"
                : "border-rail text-mute hover:text-frost"
            }`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
        <input
          className="ml-auto w-64 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
          placeholder="裁决备注（可选）"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          type="button"
          className="rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost"
          onClick={() => void load(tab)}
        >
          刷新
        </button>
      </div>

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection title={`审批（${rows.length}）`}>
        <ConsoleTable
          rows={rows}
          rowKey={(row) => row.approval_id}
          loading={loading}
          empty="暂无审批"
          columns={[
            { key: "title", header: "标题", render: (row) => row.title },
            {
              key: "tier",
              header: "档位",
              render: (row) => <ConsoleTag>{row.tier}</ConsoleTag>,
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <ConsoleTag tone={STATUS_TONE[row.status] || "default"}>
                  {row.status}
                </ConsoleTag>
              ),
            },
            {
              key: "task",
              header: "任务",
              render: (row) => (
                <span className="font-mono text-[11px]">{row.task_id}</span>
              ),
            },
            {
              key: "requester",
              header: "发起人",
              render: (row) => (
                <span className="font-mono text-[11px] text-mute">
                  {row.requester_id || "—"}
                </span>
              ),
            },
            {
              key: "time",
              header: "创建时间",
              render: (row) => (
                <span className="text-[11px] text-mute">{timeText(row.created_at)}</span>
              ),
            },
            {
              key: "act",
              header: "操作",
              render: (row) =>
                row.status === "pending" ? (
                  <span className="flex gap-1.5">
                    <button
                      type="button"
                      className="rounded border border-mint/50 px-2 py-0.5 text-[11px] text-mint hover:bg-mint/10 disabled:opacity-40"
                      disabled={!can("hitl_resolve")}
                      onClick={() => void resolve(row, true)}
                    >
                      通过
                    </button>
                    <button
                      type="button"
                      className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                      disabled={!can("hitl_resolve")}
                      onClick={() => void resolve(row, false)}
                    >
                      拒绝
                    </button>
                  </span>
                ) : (
                  <span className="text-[11px] text-mute">
                    {row.resolution_note || "—"}
                  </span>
                ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
