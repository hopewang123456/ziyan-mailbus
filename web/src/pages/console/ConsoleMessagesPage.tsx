import { useCallback, useState } from "react";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { ConsoleDrawer } from "../../components/console/ConsoleDrawer";
import { Dialog } from "../../components/console/ConsoleDialog";
import { useLiveMessages, useMessage, useTrace } from "../../lib/message/hooks";
import { sendMessage, deleteMessage } from "../../lib/message/api";
import type { MessageIn } from "../../lib/message/view";

/** 消息中心：列表、筛选、发送对话框、详情抽屉（含 trace 时间线）+ 实时 SSE 插入。 */

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleMessagesPage({ can }: { can: (capability: string) => boolean }) {
  // === 筛选条件 ===
  const [employeeId, setEmployeeId] = useState<string | null>(null);
  const [channel, setChannel] = useState<"file_bus" | "a2a" | "mcp" | null>(null);
  const [kind, setKind] = useState<string | null>(null);

  const { items: messages, total, loading, error, refresh, streamState } = useLiveMessages({
    employee_id: employeeId,
    channel,
    kind,
    limit: 100,
    offset: 0,
  });
  const streamText =
    streamState === "live" ? "实时已连接"
    : streamState === "lost" ? "实时中断，重连中"
    : streamState === "expired" ? "登录已过期"
    : streamState === "connecting" ? "实时连接中"
    : "实时未连接";

  // === 详情抽屉 ===
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useMessage(selectedId);
  const { data: trace } = useTrace(selectedId);

  // === 发送对话框 ===
  const [sendOpen, setSendOpen] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const [recipient, setRecipient] = useState("");
  const [sendKind, setSendKind] = useState("note");
  const [body, setBody] = useState("");

  const [deleteMsg, setDeleteMsg] = useState("");

  const openDetail = (row: any) => {
    setSelectedId(row.message_id);
  };

  const closeDetail = () => {
    setSelectedId(null);
  };

  const handleSend = useCallback(async () => {
    setSendErr("");
    if (!body.trim()) {
      setSendErr("消息内容不能为空");
      return;
    }
    const payload: MessageIn = {
      body: body.trim(),
      channel: "file_bus",
      kind: sendKind.trim() || "note",
      recipient_id: recipient.trim() || null,
    };
    const result = await sendMessage(payload);
    if (!result.ok) {
      setSendErr(result.error);
      return;
    }
    setSendOpen(false);
    setBody("");
    setRecipient("");
    setSendKind("note");
    void refresh();
  }, [body, sendKind, recipient, refresh]);

  const handleDelete = useCallback(
    async (row: any) => {
      const result = await deleteMessage(row.message_id);
      if (!result.ok) {
        setDeleteMsg(`删除失败：${result.error}`);
        return;
      }
      if (selectedId === row.message_id) setSelectedId(null);
      setDeleteMsg(`已删除 ${row.message_id}`);
      void refresh();
    },
    [selectedId, refresh],
  );

  return (
    <>
      <ConsolePageHeader
        title="消息中心"
        description="消息检索 + 发送 + 投递追迹"
        actions={
          <span className="flex items-center gap-2">
            <ConsoleTag
              tone={streamState === "live" ? "ok" : streamState === "expired" ? "danger" : "warn"}
            >
              {streamText}
            </ConsoleTag>
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={!can("message_send")}
              onClick={() => setSendOpen(true)}
            >
              发送消息
            </button>
          </span>
        }
      />
      {error && <p className="mb-3 text-xs text-flare">{error}</p>}
      {deleteMsg && <p className="mb-3 text-xs text-mint">{deleteMsg}</p>}

      {/* === 筛选区 === */}
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-mute">
          参与人
          <input
            className="mt-1 block w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="employee_id"
            value={employeeId ?? ""}
            onChange={(e) => setEmployeeId(e.target.value || null)}
          />
        </label>
        <label className="text-[11px] text-mute">
          通道
          <select
            className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            value={channel ?? ""}
            onChange={(e) => setChannel((e.target.value as any) || null)}
          >
            <option value="">全部</option>
            <option value="file_bus">文件总线</option>
            <option value="a2a">A2A</option>
            <option value="mcp">MCP</option>
          </select>
        </label>
        <label className="text-[11px] text-mute">
          类型
          <input
            className="mt-1 block w-24 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
            placeholder="kind"
            value={kind ?? ""}
            onChange={(e) => setKind(e.target.value || null)}
          />
        </label>
        <button type="button" className="hud-btn text-xs" onClick={() => void refresh()}>
          刷新
        </button>
      </div>

      {/* === 消息列表 === */}
      <ConsoleSection title={`消息（${messages.length} / ${total}）`}>
        <ConsoleTable
          rows={messages}
          rowKey={(row: any) => row.message_id}
          loading={loading}
          empty="暂无消息"
          onRowClick={(row: any) => openDetail(row)}
          selectedKey={selectedId ?? undefined}
          columns={[
            {
              key: "time",
              header: "时间",
              render: (row: any) => (
                <span className="text-[11px] text-mute">{timeText(row.created_at)}</span>
              ),
            },
            {
              key: "sender",
              header: "发送人",
              render: (row: any) => <span className="font-mono text-[11px]">{row.sender_id}</span>,
            },
            {
              key: "recipient",
              header: "接收人",
              render: (row: any) => (
                <span className="font-mono text-[11px]">{row.recipient_id || "广播"}</span>
              ),
            },
            { key: "kind", header: "类型", render: (row: any) => <ConsoleTag>{row.kind}</ConsoleTag> },
            {
              key: "channel",
              header: "通道",
              render: (row: any) => <ConsoleTag tone="default">{row.channel}</ConsoleTag>,
            },
            {
              key: "body",
              header: "内容",
              render: (row: any) => <span className="text-mute">{row.body.slice(0, 60)}</span>,
            },
            {
              key: "status",
              header: "投递",
              render: (row: any) => {
                const value = row.delivery_status || "pending";
                const tone =
                  value === "delivered" ? "ok" : value === "failed" ? "danger" : "warn";
                return <ConsoleTag tone={tone as "ok" | "danger" | "warn"}>{value}</ConsoleTag>;
              },
            },
            {
              key: "act",
              header: "操作",
              render: (row: any) => (
                <button
                  type="button"
                  className="rounded border border-flare/50 px-2 py-0.5 text-[11px] text-flare hover:bg-flare/10 disabled:opacity-40"
                  disabled={!can("system_config")}
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleDelete(row);
                  }}
                >
                  删除
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {/* === 详情抽屉 === */}
      {selectedId && (
        <ConsoleDrawer open onClose={closeDetail} title={`消息详情 · ${selectedId}`}>
          {detail && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <Field label="发送人" value={detail.sender_id} />
                <Field label="接收人" value={detail.recipient_id || "广播"} />
                <Field label="类型" value={detail.kind} />
                <Field label="通道" value={detail.channel} />
                <Field label="投递状态" value={detail.delivery_status || "pending"} />
                <Field label="创建时间" value={timeText(detail.created_at)} />
                {detail.pair_id && <Field label="结对" value={detail.pair_id} />}
                {detail.task_id && <Field label="任务" value={detail.task_id} />}
              </div>
              <div>
                <p className="mb-1 text-[11px] text-mute">正文</p>
                <pre className="rounded border border-rail bg-hull px-2 py-1 text-xs text-frost whitespace-pre-wrap break-all">
                  {detail.body}
                </pre>
              </div>
            </div>
          )}
          <div className="mt-4">
            <p className="mb-2 text-[11px] text-mute">投递追迹时间线</p>
            {trace?.events && trace.events.length > 0 ? (
              <ol className="space-y-1">
                {trace.events.map((evt: any, idx: number) => (
                  <li key={idx} className="flex gap-2 text-[11px]">
                    <span className="w-20 shrink-0 text-mute">{timeText(evt.at)}</span>
                    <span className="font-mono">{evt.status}</span>
                    {evt.error_code && (
                      <span className="font-mono text-flare">{evt.error_code}</span>
                    )}
                    {evt.channel && <span className="text-mute">· {evt.channel}</span>}
                    {evt.detail && (
                      <span className="text-mute">
                        · {JSON.stringify(evt.detail).slice(0, 40)}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-[11px] text-mute">暂无追迹事件</p>
            )}
          </div>
        </ConsoleDrawer>
      )}

      {/* === 发送对话框 === */}
      {sendOpen && (
        <Dialog open title="发送消息" onClose={() => setSendOpen(false)}>
          <div className="space-y-3">
            <div className="flex gap-2">
              <label className="flex-1 text-[11px] text-mute">
                接收人
                <input
                  className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                  placeholder="留空 = 广播"
                  value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}
                />
              </label>
              <label className="w-32 text-[11px] text-mute">
                类型
                <input
                  className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                  value={sendKind}
                  onChange={(e) => setSendKind(e.target.value)}
                />
              </label>
            </div>
            <label className="block text-[11px] text-mute">
              消息正文
              <textarea
                className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
                rows={4}
                placeholder="要发送的消息正文"
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
            </label>
            {sendErr && <p className="text-xs text-flare">{sendErr}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                onClick={() => setSendOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded bg-mint px-3 py-1.5 text-xs text-abyss hover:opacity-90 disabled:opacity-40"
                disabled={!can("message_send")}
                onClick={() => void handleSend()}
              >
                发送
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-mute">{label}</p>
      <p className="font-mono text-frost break-all">{value}</p>
    </div>
  );
}
