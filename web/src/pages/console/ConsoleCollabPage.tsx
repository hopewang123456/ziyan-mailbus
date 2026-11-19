import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import { useCollabStream, useScreenSync } from "../../twin/collab";
import type { OfficeSite } from "../../twin/types";

/**
 * 协同管理端：在线员工、A2A 消息、任务接力与大屏协同。
 * 只使用 staff / layout / messages / tasks 的真实数据，不再提供本地演示或虚构结对。
 */

type Tab = "staff" | "messages" | "tasks" | "screens";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "staff", label: "在线员工" },
  { key: "messages", label: "A2A 消息" },
  { key: "tasks", label: "任务接力" },
  { key: "screens", label: "大屏协同" },
];

type Staff = {
  employee_id: string;
  display_name: string;
  status: string;
  team_id?: string | null;
  position_id?: string | null;
  seat_id?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_framework?: string | null;
};

type Message = {
  message_id: string;
  sender_id: string;
  recipient_id?: string | null;
  kind: string;
  body: string;
  created_at?: string | null;
  delivery_status?: string | null;
};

type Task = {
  task_id: string;
  title: string;
  state: string;
  owner_id?: string | null;
  updated_at?: string | null;
  nodes?: Array<{ node_id: string; name: string; state: string }>;
};

type Screen = {
  screen_id: string;
  name: string;
  floor_id?: string | null;
  seat_id?: string | null;
  online: boolean;
  last_seen?: string | null;
};

const TASK_STATE_LABEL: Record<string, string> = {
  draft: "草稿",
  queued: "待派发",
  running: "执行中",
  blocked: "阻塞",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

function timeText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function ConsoleCollabPage({ can }: { can: (capability: string) => boolean }) {
  const [tab, setTab] = useState<Tab>("staff");
  const [staff, setStaff] = useState<Staff[]>([]);
  const [site, setSite] = useState<OfficeSite | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [screens, setScreens] = useState<Screen[]>([]);
  const [focusDraft, setFocusDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [toEmployee, setToEmployee] = useState("");
  const [body, setBody] = useState("");

  // 管理端只作为遥控方，不登记成一块大屏
  const { peers, sendView } = useScreenSync(() => {}, { register: false });

  const load = useCallback(async () => {
    setLoading(true);
    const [staffRes, layoutRes, messageRes, taskRes, screenRes] = await Promise.all([
      api<Staff[]>("/api/identity/staff?status=active"),
      api<OfficeSite>("/api/layout"),
      api<Message[]>("/api/messages?limit=50"),
      api<Task[]>("/api/tasks"),
      api<Screen[]>("/api/collab/screens"),
    ]);
    setLoading(false);

    const errors: string[] = [];
    if (staffRes.ok && Array.isArray(staffRes.data)) setStaff(staffRes.data);
    else if (!staffRes.ok) errors.push(`员工：${staffRes.error}`);
    if (layoutRes.ok) setSite(layoutRes.data);
    else errors.push(`布局：${layoutRes.error}`);
    if (messageRes.ok && Array.isArray(messageRes.data)) setMessages(messageRes.data);
    else if (!messageRes.ok) errors.push(`消息：${messageRes.error}`);
    if (taskRes.ok && Array.isArray(taskRes.data)) setTasks(taskRes.data);
    else if (!taskRes.ok) errors.push(`任务：${taskRes.error}`);
    if (screenRes.ok && Array.isArray(screenRes.data)) setScreens(screenRes.data);
    setErr(errors.join("；"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 协同事件推送：接口缺失时静默，保留手动刷新
  const reloadTimer = useRef(0);
  const streamLive = useCollabStream(true, (event) => {
    if (!/^(message|task|pair|screen)\./.test(event)) return;
    if (reloadTimer.current) return;
    reloadTimer.current = window.setTimeout(() => {
      reloadTimer.current = 0;
      void load();
    }, 400);
  });
  useEffect(
    () => () => {
      if (reloadTimer.current) window.clearTimeout(reloadTimer.current);
    },
    [],
  );

  const nameOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const person of staff) {
      map.set(person.employee_id, person.display_name);
      if (person.agent_id) map.set(person.agent_id, person.agent_name || person.display_name);
    }
    for (const floor of site?.floors ?? []) {
      for (const room of floor.rooms) {
        for (const seat of room.seats) {
          if (!seat.agent) continue;
          map.set(seat.seat_id, seat.agent.display_name);
          if (seat.agent.agent_id) {
            map.set(seat.agent.agent_id, seat.agent.agent_name || seat.agent.display_name);
          }
        }
      }
    }
    return map;
  }, [staff, site]);

  const displayName = (id?: string | null) => (id ? nameOf.get(id) ?? id : "广播");

  const online = staff.filter((person) => person.status === "active");
  const running = tasks.filter((task) => !/done|failed|cancel/.test(task.state));
  const onlineScreens = screens.filter((screen) => screen.online).length;
  const canSend = can("message_send");

  async function focusScreen(screen: Screen) {
    setErr("");
    setMsg("");
    const floorId = focusDraft[screen.screen_id] || site?.floors[0]?.floor_id || "";
    if (!floorId) {
      setErr("请选择要聚焦的楼层");
      return;
    }
    const result = await api(
      `/api/collab/screens/${encodeURIComponent(screen.screen_id)}/focus`,
      { method: "POST", body: JSON.stringify({ floor_id: floorId, seat_id: null }) },
    );
    if (!result.ok) {
      setErr(`大屏遥控：${result.error}`);
      return;
    }
    setMsg(`已向「${screen.name}」下发聚焦 ${floorId}`);
    await load();
  }

  async function sendMessage() {
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
        recipient_id: toEmployee || null,
        kind: "note",
        channel: "file_bus",
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(toEmployee ? `已发送给 ${displayName(toEmployee)}` : "已广播给全部员工");
    setBody("");
    await load();
  }

  return (
    <>
      <ConsolePageHeader
        title="协同管理"
        description="在线员工、A2A 消息与任务接力的真实数据；大屏只同步聚焦位置，不伪造业务内容"
        actions={
          <>
            <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
              刷新
            </button>
            <button
              type="button"
              className="hud-btn text-xs"
              onClick={() => window.open("/twin", "_blank", "noopener")}
            >
              打开孪生大屏 ↗
            </button>
          </>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "在职员工", value: online.length },
          { label: "进行中任务", value: running.length },
          { label: "最近消息", value: messages.length },
          { label: "在线大屏", value: screens.length ? onlineScreens : peers + 1 },
        ].map((item) => (
          <div key={item.label} className="rounded-lg border border-rail bg-hull/60 px-4 py-3">
            <p className="text-[10px] uppercase tracking-widest text-mute">{item.label}</p>
            <p className="mt-1 font-display text-xl text-frost">{item.value}</p>
          </div>
        ))}
      </div>

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
      </div>

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      {tab === "staff" && (
        <ConsoleSection title={`在线员工（${online.length}）`}>
          <ConsoleTable
            rows={online}
            rowKey={(row) => row.employee_id}
            loading={loading}
            empty="暂无在职员工"
            columns={[
              { key: "name", header: "员工", render: (row) => row.display_name },
              {
                key: "agent",
                header: "Agent",
                render: (row) => (
                  <span>
                    {row.agent_name || row.agent_id || "—"}
                    {row.agent_framework ? (
                      <ConsoleTag>{row.agent_framework}</ConsoleTag>
                    ) : null}
                  </span>
                ),
              },
              { key: "team", header: "团队", render: (row) => row.team_id || "—" },
              { key: "position", header: "岗位", render: (row) => row.position_id || "—" },
              { key: "seat", header: "工位", render: (row) => <span className="font-mono">{row.seat_id || "—"}</span> },
            ]}
          />
        </ConsoleSection>
      )}

      {tab === "messages" && (
        <>
          <ConsoleSection title="发送 A2A 消息">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-mute">
                接收员工
                <select
                  className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={toEmployee}
                  onChange={(event) => setToEmployee(event.target.value)}
                >
                  <option value="">广播给全部员工</option>
                  {staff.map((person) => (
                    <option key={person.employee_id} value={person.employee_id}>
                      {person.display_name} · {person.employee_id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex-1 text-[11px] text-mute">
                消息内容
                <input
                  className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={body}
                  maxLength={500}
                  placeholder="例如：三点的评审请准时参加"
                  onChange={(event) => setBody(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={!canSend}
                onClick={() => void sendMessage()}
              >
                发送
              </button>
            </div>
            {!canSend && (
              <p className="mt-2 text-[11px] text-amber-signal">发送消息需要 message_send。</p>
            )}
          </ConsoleSection>

          <ConsoleSection title={`消息记录（${messages.length}）`}>
            <ConsoleTable
              rows={messages}
              rowKey={(row) => row.message_id}
              loading={loading}
              empty="暂无消息"
              columns={[
                { key: "time", header: "时间", render: (row) => timeText(row.created_at) },
                { key: "from", header: "发送方", render: (row) => displayName(row.sender_id) },
                { key: "to", header: "接收方", render: (row) => displayName(row.recipient_id) },
                { key: "kind", header: "类型", render: (row) => <ConsoleTag>{row.kind}</ConsoleTag> },
                {
                  key: "body",
                  header: "内容",
                  render: (row) => <span className="text-frost/80">{row.body}</span>,
                },
                {
                  key: "status",
                  header: "投递",
                  render: (row) => (
                    <ConsoleTag
                      tone={
                        row.delivery_status === "failed"
                          ? "danger"
                          : row.delivery_status === "pending"
                            ? "warn"
                            : "ok"
                      }
                    >
                      {row.delivery_status || "—"}
                    </ConsoleTag>
                  ),
                },
              ]}
            />
          </ConsoleSection>
        </>
      )}

      {tab === "tasks" && (
        <ConsoleSection
          title={`任务接力（${tasks.length}）`}
          actions={
            <a
              href="/console/tasks"
              className="rounded border border-rail px-2.5 py-1 text-xs text-mute hover:text-frost"
            >
              去任务页操作 →
            </a>
          }
        >
          <ConsoleTable
            rows={tasks}
            rowKey={(row) => row.task_id}
            loading={loading}
            empty="暂无任务"
            columns={[
              { key: "title", header: "任务", render: (row) => row.title },
              {
                key: "state",
                header: "状态",
                render: (row) => (
                  <ConsoleTag
                    tone={
                      /done/.test(row.state)
                        ? "ok"
                        : /failed|cancel/.test(row.state)
                          ? "danger"
                          : /blocked|queued/.test(row.state)
                            ? "warn"
                            : "default"
                    }
                  >
                    {TASK_STATE_LABEL[row.state] ?? row.state}
                  </ConsoleTag>
                ),
              },
              {
                key: "node",
                header: "当前节点",
                render: (row) => {
                  const active = row.nodes?.find((node) => node.state === "running") ?? row.nodes?.[0];
                  return active ? `${active.name} · ${TASK_STATE_LABEL[active.state] ?? active.state}` : "—";
                },
              },
              { key: "owner", header: "负责人", render: (row) => displayName(row.owner_id) },
              { key: "time", header: "更新时间", render: (row) => timeText(row.updated_at) },
            ]}
          />
        </ConsoleSection>
      )}

      {tab === "screens" && (
        <>
          <ConsoleSection
            title={`大屏登记（${screens.length}）`}
            actions={
              <ConsoleTag tone={streamLive ? "ok" : "warn"}>
                {streamLive ? "SSE 实时" : "轮询"}
              </ConsoleTag>
            }
          >
            {screens.length ? (
              <ConsoleTable
                rows={screens}
                rowKey={(row) => row.screen_id}
                loading={loading}
                empty="暂无登记大屏"
                columns={[
                  { key: "name", header: "大屏", render: (row) => row.name },
                  {
                    key: "floor",
                    header: "当前楼层",
                    render: (row) =>
                      (site?.floors ?? []).find((floor) => floor.floor_id === row.floor_id)?.name ??
                      row.floor_id ??
                      "整楼",
                  },
                  {
                    key: "online",
                    header: "状态",
                    render: (row) => (
                      <ConsoleTag tone={row.online ? "ok" : "default"}>
                        {row.online ? "在线" : "离线"}
                      </ConsoleTag>
                    ),
                  },
                  { key: "seen", header: "最近心跳", render: (row) => timeText(row.last_seen) },
                  {
                    key: "act",
                    header: "遥控聚焦",
                    render: (row) => (
                      <span className="flex items-center gap-1">
                        <select
                          className="w-32 rounded border border-rail bg-hull px-1.5 py-0.5 text-[11px] text-frost"
                          value={focusDraft[row.screen_id] ?? row.floor_id ?? site?.floors[0]?.floor_id ?? ""}
                          onChange={(event) =>
                            setFocusDraft((prev) => ({
                              ...prev,
                              [row.screen_id]: event.target.value,
                            }))
                          }
                        >
                          {(site?.floors ?? []).map((floor) => (
                            <option key={floor.floor_id} value={floor.floor_id}>
                              {floor.level}F · {floor.name.split(" · ")[1] ?? floor.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                          onClick={() => void focusScreen(row)}
                        >
                          聚焦
                        </button>
                      </span>
                    ),
                  },
                ]}
              />
            ) : (
              <p className="text-xs leading-relaxed text-mute">
                后端尚未提供大屏登记接口（GET /api/collab/screens）。大屏打开后会尝试登记并上报心跳；
                接口上线前仍可用下方本机广播。
              </p>
            )}
          </ConsoleSection>

          <ConsoleSection title={`本机大屏（×${peers + 1}）`}>
            <p className="mb-3 text-xs leading-relaxed text-mute">
              同一浏览器内打开的孪生大屏通过 BroadcastChannel 同步聚焦楼层与员工；
              跨设备同步依赖上方的屏幕登记 + screen.focus 推送。
            </p>
            <div className="flex flex-wrap gap-2">
              {(site?.floors ?? []).map((floor) => (
                <button
                  key={floor.floor_id}
                  type="button"
                  className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                  onClick={() => {
                    sendView({ floorId: floor.floor_id, seatId: null });
                    setMsg(`已广播聚焦 ${floor.level}F · ${floor.name}`);
                  }}
                >
                  聚焦 {floor.level}F · {floor.name.split(" · ")[1] ?? floor.name}
                </button>
              ))}
              <button
                type="button"
                className="rounded border border-rail px-3 py-1.5 text-xs text-mute hover:text-frost"
                onClick={() => {
                  sendView({ floorId: null, seatId: null });
                  setMsg("已广播返回整楼");
                }}
              >
                返回整楼
              </button>
            </div>
            {!site && !loading && (
              <p className="mt-3 text-xs text-flare">布局接口不可用，无法列出楼层。</p>
            )}
          </ConsoleSection>
        </>
      )}
    </>
  );
}
