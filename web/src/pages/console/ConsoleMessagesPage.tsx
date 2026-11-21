import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 消息与日志追迹：消息检索（超管全部 / 普通用户自己收发）+ 投递尝试 + 操作日志。 */

type Message = {
  message_id: string;
  sender_id: string;
  recipient_id?: string | null;
  kind: string;
  body: string;
  created_at?: string | null;
  delivery_status?: string | null;
};

type Attempt = {
  message_id: string;
  attempt_no: number;
  ok: boolean;
  error_code?: string | null;
  detail?: string | null;
  at?: string | null;
};

type LogEntry = {
  event_id: string;
  kind: string;
  payload: Record<string, unknown>;
  attempts: number;
  created_at?: string | null;
};

type StatusFilter = "" | "pending" | "delivered" | "failed";

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleMessagesPage({ can }: { can: (capability: string) => boolean }) {
  const [scope, setScope] = useState<"all" | "inbox">("all");
  const [agent, setAgent] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [since, setSince] = useState("");
  const [limit, setLimit] = useState(100);
  const [recipient, setRecipient] = useState("");
  const [kind, setKind] = useState("note");
  const [body, setBody] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [selected, setSelected] = useState<Message | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (agent.trim()) params.set("agent", agent.trim());
    if (status) params.set("status", status);
    if (since) params.set("since", new Date(since).toISOString());
    params.set("limit", String(limit));
    const [m, l] = await Promise.all([
      scope === "inbox"
        ? api<Message[]>("/api/inbox")
        : api<Message[]>(`/api/messages?${params.toString()}`),
      api<LogEntry[]>("/api/log?limit=50"),
    ]);
    setLoading(false);
    if (m.ok) setMessages(m.data);
    if (l.ok) setLogs(l.data);
    const errors = [m, l]
      .filter((result) => !result.ok)
      .map((result) => (result.ok ? "" : result.error));
    setErr(errors.filter(Boolean).join("; "));
  };

  useEffect(() => {
    void load();
  }, [scope]);

  async function openMessage(row: Message) {
    setSelected(row);
    setAttempts([]);
    const result = await api<Attempt[]>(
      `/api/messages/${encodeURIComponent(row.message_id)}/attempts`,
    );
    if (result.ok) setAttempts(result.data);
    else setErr(result.error);
  }

  async function send() {
    setErr("");
    setMsg("");
    if (!body.trim()) {
      setErr("消息内容不能为空");
      return;
    }
    const result = await api<Message>("/api/messages", {
      method: "POST",
      body: JSON.stringify({
        body: body.trim(),
        recipient_id: recipient.trim() || null,
        kind: kind.trim() || "note",
        channel: "file_bus",
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(
      recipient.trim() ? `已发送给 ${recipient.trim()}` : "已广播给全部员工",
    );
    setBody("");
    await load();
  }

  async function remove(row: Message) {
    setErr("");
    setMsg("");
    const result = await api(
      `/api/messages/${encodeURIComponent(row.message_id)}`,
      { method: "DELETE" },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    if (selected?.message_id === row.message_id) {
      setSelected(null);
      setAttempts([]);
    }
    setMsg(`已删除消息 ${row.message_id}`);
    await load();
  }

  return (
    <>
      <ConsolePageHeader
        title="消息与日志追迹"
        description="全部消息按参与人/状态/时间检索；我的收件箱只显示发给我的消息；点击行查看投递尝试"
      />

      <ConsoleSection title="发送消息">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-mute">
            接收人
            <input
              className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              placeholder="留空 = 广播"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-mute">
            类型
            <input
              className="mt-1 block w-24 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            />
          </label>
          <label className="flex-1 text-[11px] text-mute">
            内容
            <input
              className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              placeholder="要发送的消息正文"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void send();
              }}
            />
          </label>
          <button
            type="button"
            className="hud-btn text-xs disabled:opacity-40"
            disabled={!can("message_send")}
            onClick={() => void send()}
          >
            发送
          </button>
        </div>
      </ConsoleSection>

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-mute">
          范围
          <select
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={scope}
            onChange={(e) => setScope(e.target.value as "all" | "inbox")}
          >
            <option value="all">全部消息</option>
            <option value="inbox">我的收件箱</option>
          </select>
        </label>
        <label className="text-[11px] text-mute">
          参与人
          <input
            className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="employee_id"
            disabled={scope === "inbox"}
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
          />
        </label>
        <label className="text-[11px] text-mute">
          投递状态
          <select
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            disabled={scope === "inbox"}
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            <option value="">全部</option>
            <option value="pending">未投递</option>
            <option value="delivered">已送达</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <label className="text-[11px] text-mute">
          起始时间
          <input
            type="datetime-local"
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            disabled={scope === "inbox"}
            value={since}
            onChange={(e) => setSince(e.target.value)}
          />
        </label>
        <label className="text-[11px] text-mute">
          条数
          <input
            type="number"
            min={1}
            max={500}
            className="mt-1 block w-20 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            disabled={scope === "inbox"}
            value={limit}
            onChange={(e) =>
              setLimit(Math.max(1, Math.min(500, Number(e.target.value) || 100)))
            }
          />
        </label>
        <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
          查询
        </button>
      </div>

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection title={`${scope === "inbox" ? "收件箱" : "消息"}（${messages.length}）`}>
        <ConsoleTable
          rows={messages}
          rowKey={(row) => row.message_id}
          loading={loading}
          empty="暂无消息"
          onRowClick={(row) => void openMessage(row)}
          selectedKey={selected?.message_id}
          columns={[
            {
              key: "time",
              header: "时间",
              render: (row) => (
                <span className="text-[11px] text-mute">{timeText(row.created_at)}</span>
              ),
            },
            {
              key: "sender",
              header: "发送人",
              render: (row) => (
                <span className="font-mono text-[11px]">{row.sender_id}</span>
              ),
            },
            {
              key: "recipient",
              header: "接收人",
              render: (row) => (
                <span className="font-mono text-[11px]">
                  {row.recipient_id || "广播"}
                </span>
              ),
            },
            { key: "kind", header: "类型", render: (row) => <ConsoleTag>{row.kind}</ConsoleTag> },
            {
              key: "body",
              header: "内容",
              render: (row) => <span className="text-mute">{row.body.slice(0, 60)}</span>,
            },
            {
              key: "status",
              header: "投递",
              render: (row) => {
                const value = row.delivery_status || "pending";
                const tone =
                  value === "delivered" ? "ok" : value === "failed" ? "danger" : "warn";
                return <ConsoleTag tone={tone}>{value}</ConsoleTag>;
              },
            },
            {
              key: "act",
              header: "操作",
              render: (row) => (
                <button
                  type="button"
                  className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                  disabled={!can("system_config")}
                  onClick={(event) => {
                    event.stopPropagation();
                    void remove(row);
                  }}
                >
                  删除
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {selected && (
        <ConsoleSection title={`投递尝试 · ${selected.message_id}`}>
          <ConsoleTable
            rows={attempts}
            rowKey={(row) => `${row.message_id}-${row.attempt_no}`}
            empty="暂无投递记录"
            columns={[
              { key: "no", header: "#", render: (row) => String(row.attempt_no) },
              {
                key: "ok",
                header: "结果",
                render: (row) => (
                  <ConsoleTag tone={row.ok ? "ok" : "danger"}>
                    {row.ok ? "成功" : "失败"}
                  </ConsoleTag>
                ),
              },
              {
                key: "code",
                header: "错误码",
                render: (row) => <span className="font-mono text-[11px]">{row.error_code || "—"}</span>,
              },
              {
                key: "detail",
                header: "明细",
                render: (row) => <span className="text-mute">{row.detail || "—"}</span>,
              },
              {
                key: "at",
                header: "时间",
                render: (row) => (
                  <span className="text-[11px] text-mute">{timeText(row.at)}</span>
                ),
              },
            ]}
          />
        </ConsoleSection>
      )}

      <ConsoleSection title={`操作日志（${logs.length}）`}>
        <ConsoleTable
          rows={logs}
          rowKey={(row) => row.event_id}
          empty="暂无日志"
          columns={[
            { key: "kind", header: "事件", render: (row) => <ConsoleTag>{row.kind}</ConsoleTag> },
            {
              key: "payload",
              header: "载荷",
              render: (row) => (
                <span className="font-mono text-[11px] text-mute">
                  {JSON.stringify(row.payload).slice(0, 90)}
                </span>
              ),
            },
            {
              key: "attempts",
              header: "投递次数",
              render: (row) => String(row.attempts),
            },
            {
              key: "time",
              header: "时间",
              render: (row) => (
                <span className="text-[11px] text-mute">{timeText(row.created_at)}</span>
              ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
