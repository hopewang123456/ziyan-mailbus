import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import type { OfficeSite } from "../../twin/types";

/**
 * 协同管理端：员工、结对、协同消息、任务接力与大屏遥控。
 * 数据全部来自 staff / layout / messages / tasks / collab 真实接口。
 */

type Tab = "staff" | "pairs" | "messages" | "tasks" | "screens";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "staff", label: "在线员工" },
  { key: "pairs", label: "结对协同" },
  { key: "messages", label: "结对消息" },
  { key: "tasks", label: "任务接力" },
  { key: "screens", label: "大屏遥控" },
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

type Pair = {
  pair_id: string;
  initiator_id: string;
  partner_id: string;
  state: string;
  created_at?: string | null;
  ended_at?: string | null;
};

type CollabMessage = {
  message_id: string;
  sender_id: string;
  recipient_id?: string | null;
  pair_id?: string | null;
  kind: string;
  body: string;
  created_at?: string | null;
  delivery_status?: string | null;
};

type Message = CollabMessage;

type Screen = {
  screen_id: string;
  name: string;
  floor_id?: string | null;
  seat_id?: string | null;
  online: boolean;
  last_seen?: string | null;
  secret?: string | null;
};

type Task = {
  task_id: string;
  title: string;
  state: string;
  owner_id?: string | null;
  updated_at?: string | null;
  nodes?: Array<{ node_id: string; name: string; state: string }>;
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

/** 控制台大屏标识同标签页复用，避免每次刷新都新增一条记录。 */
function getConsoleScreenId() {
  const key = "mailbus_console_screen_id";
  try {
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const id = `console_${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(key, id);
    return id;
  } catch {
    return `console_${Math.random().toString(36).slice(2, 10)}`;
  }
}

export function ConsoleCollabPage({ can }: { can: (capability: string) => boolean }) {
  const [tab, setTab] = useState<Tab>("staff");
  const [meId, setMeId] = useState("");
  const [staff, setStaff] = useState<Staff[]>([]);
  const [site, setSite] = useState<OfficeSite | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [screens, setScreens] = useState<Screen[]>([]);
  const [selectedPairId, setSelectedPairId] = useState("");
  const [pairMessages, setPairMessages] = useState<CollabMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const [partnerId, setPartnerId] = useState("");
  const [pairBody, setPairBody] = useState("");
  const [toEmployee, setToEmployee] = useState("");
  const [body, setBody] = useState("");
  const [screenName, setScreenName] = useState("");
  const [focusFloor, setFocusFloor] = useState("");

  const canSend = can("message_send");
  const canScreen = can("console_admin");

  /** 本页固定代表一块大屏：重复登记只更新同一条记录，避免列表膨胀。 */
  const screenIdRef = useRef(getConsoleScreenId());
  const screenFloorRef = useRef<string | null>(null);
  const screenSecretRef = useRef("");
  const registeredRef = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!registeredRef.current) return;
      void api(`/api/collab/screens/${encodeURIComponent(screenIdRef.current)}/heartbeat`, {
        method: "POST",
        body: JSON.stringify({
          floor_id: screenFloorRef.current,
          seat_id: null,
          ...(screenSecretRef.current ? { secret: screenSecretRef.current } : {}),
        }),
      });
    }, 25_000);
    return () => {
      window.clearInterval(timer);
      if (!registeredRef.current) return;
      registeredRef.current = false;
      const secret = screenSecretRef.current;
      void fetch(
        `/api/public/collab/screens/${encodeURIComponent(screenIdRef.current)}/leave`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(secret ? { secret } : {}),
        },
      );
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const [meRes, staffRes, layoutRes, messageRes, taskRes, pairRes, screenRes] =
      await Promise.all([
        api<{ employee_id: string }>("/api/identity/me"),
        api<Staff[]>("/api/identity/staff?status=active"),
        api<OfficeSite>("/api/layout"),
        api<Message[]>("/api/messages?limit=50"),
        api<Task[]>("/api/tasks"),
        api<Pair[]>("/api/collab/pairs"),
        api<Screen[]>("/api/collab/screens"),
      ]);
    setLoading(false);

    const errors: string[] = [];
    if (meRes.ok) setMeId(meRes.data.employee_id);
    else errors.push(`当前员工：${meRes.error}`);
    if (!staffRes.ok) errors.push(`员工：${staffRes.error}`);
    else if (Array.isArray(staffRes.data)) setStaff(staffRes.data);
    if (layoutRes.ok) {
      setSite(layoutRes.data);
      setFocusFloor((prev) => prev || layoutRes.data.floors[0]?.floor_id || "");
    } else errors.push(`布局：${layoutRes.error}`);
    if (!messageRes.ok) errors.push(`消息：${messageRes.error}`);
    else if (Array.isArray(messageRes.data)) setMessages(messageRes.data);
    if (!taskRes.ok) errors.push(`任务：${taskRes.error}`);
    else if (Array.isArray(taskRes.data)) setTasks(taskRes.data);
    if (!pairRes.ok) errors.push(`结对：${pairRes.error}`);
    else if (Array.isArray(pairRes.data)) setPairs(pairRes.data);
    if (!screenRes.ok) errors.push(`大屏：${screenRes.error}`);
    else if (Array.isArray(screenRes.data)) setScreens(screenRes.data);
    setErr(errors.join("；"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 静默刷新：大屏在线状态与协同消息不依赖事件推送，定时同步且不打断当前操作。 */
  const refreshSilently = useCallback(async () => {
    const [screenRes, pairRes, messageRes] = await Promise.all([
      api<Screen[]>("/api/collab/screens"),
      api<Pair[]>("/api/collab/pairs"),
      api<Message[]>("/api/messages?limit=50"),
    ]);
    if (screenRes.ok && Array.isArray(screenRes.data)) setScreens(screenRes.data);
    if (pairRes.ok && Array.isArray(pairRes.data)) setPairs(pairRes.data);
    if (messageRes.ok && Array.isArray(messageRes.data)) setMessages(messageRes.data);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void refreshSilently();
    }, 20_000);
    const onVisibility = () => {
      if (!document.hidden) void refreshSilently();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshSilently]);

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
        }
      }
    }
    return map;
  }, [staff, site]);

  const displayName = (id?: string | null) => (id ? nameOf.get(id) ?? id : "—");
  const activePairs = pairs.filter((pair) => pair.state === "active");

  const openPair = async (pairId: string) => {
    setSelectedPairId(pairId);
    setErr("");
    const result = await api<CollabMessage[]>(
      `/api/collab/messages?pair_id=${encodeURIComponent(pairId)}&limit=100`,
    );
    if (result.ok && Array.isArray(result.data)) setPairMessages(result.data);
    else {
      setPairMessages([]);
      if (!result.ok) setErr(`结对消息：${result.error}`);
    }
  };

  async function createPair() {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api<Pair>("/api/collab/pairs", {
      method: "POST",
      body: JSON.stringify({ partner_id: partnerId }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已发起与 ${displayName(partnerId)} 的结对`);
    setPartnerId("");
    await load();
    await openPair(result.data.pair_id);
  }

  async function endPair(pairId: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api(`/api/collab/pairs/${encodeURIComponent(pairId)}/end`, {
      method: "POST",
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg("结对已结束");
    if (selectedPairId === pairId) setPairMessages([]);
    await load();
  }

  async function sendPairMessage() {
    setErr("");
    setMsg("");
    if (!selectedPairId) {
      setErr("请先选择一个结对");
      return;
    }
    if (!pairBody.trim()) {
      setErr("消息内容不能为空");
      return;
    }
    const result = await api<CollabMessage>("/api/collab/messages", {
      method: "POST",
      body: JSON.stringify({
        pair_id: selectedPairId,
        body: pairBody.trim(),
        kind: "note",
        channel: "file_bus",
      }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPairBody("");
    setMsg("协同消息已发送");
    await openPair(selectedPairId);
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

  async function registerScreen() {
    setBusy(true);
    setErr("");
    setMsg("");
    if (!screenName.trim()) {
      setBusy(false);
      setErr("大屏名称不能为空");
      return;
    }
    const floor = focusFloor || null;
    const result = await api<Screen>("/api/collab/screens", {
      method: "POST",
      body: JSON.stringify({
        screen_id: screenIdRef.current,
        name: screenName.trim(),
        floor_id: floor,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    screenFloorRef.current = floor;
    // M14：管理员登记会一次性回显密钥，后续心跳/离线必须携带
    screenSecretRef.current = result.data.secret ?? "";
    registeredRef.current = true;
    setScreenName("");
    setMsg("大屏已登记，本页将持续发送心跳");
    await load();
  }

  async function leaveScreen(screenId: string) {
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api(
      `/api/collab/screens/${encodeURIComponent(screenId)}/leave`,
      { method: "POST" },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    if (screenId === screenIdRef.current) registeredRef.current = false;
    setMsg(`已将 ${screenId} 置为离线`);
    await load();
  }

  async function focusScreen(screenId: string) {
    if (!focusFloor) {
      setErr("请先选择楼层");
      return;
    }
    setBusy(true);
    setErr("");
    setMsg("");
    const result = await api(
      `/api/collab/screens/${encodeURIComponent(screenId)}/focus`,
      {
        method: "POST",
        body: JSON.stringify({ floor_id: focusFloor, seat_id: null }),
      },
    );
    setBusy(false);
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setMsg(`已遥控 ${screenId} 聚焦所选楼层`);
    await load();
  }

  const online = staff.filter((person) => person.status === "active");
  const running = tasks.filter((task) => !/done|failed|cancel/.test(task.state));

  return (
    <>
      <ConsolePageHeader
        title="协同管理"
        description="结对、协同消息、任务接力与大屏遥控；全部来自真实接口，不生成演示数据"
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
          { label: "活跃结对", value: activePairs.length },
          { label: "在线大屏", value: screens.filter((screen) => screen.online).length },
          { label: "进行中任务", value: running.length },
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
                    {row.agent_framework ? <ConsoleTag>{row.agent_framework}</ConsoleTag> : null}
                  </span>
                ),
              },
              { key: "team", header: "团队", render: (row) => row.team_id || "—" },
              { key: "position", header: "岗位", render: (row) => row.position_id || "—" },
              {
                key: "seat",
                header: "工位",
                render: (row) => <span className="font-mono">{row.seat_id || "—"}</span>,
              },
            ]}
          />
        </ConsoleSection>
      )}

      {tab === "pairs" && (
        <>
          <ConsoleSection title="发起结对">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-mute">
                结对对象
                <select
                  className="mt-1 block min-w-48 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={partnerId}
                  onChange={(event) => setPartnerId(event.target.value)}
                >
                  <option value="">选择员工</option>
                  {staff
                    .filter((person) => person.employee_id !== meId)
                    .map((person) => (
                      <option key={person.employee_id} value={person.employee_id}>
                        {person.display_name} · {person.employee_id}
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={busy || !partnerId}
                onClick={() => void createPair()}
              >
                发起结对
              </button>
            </div>
          </ConsoleSection>

          <ConsoleSection title={`结对记录（${pairs.length}）`}>
            <ConsoleTable
              rows={pairs}
              rowKey={(row) => row.pair_id}
              loading={loading}
              empty="暂无结对"
              columns={[
                {
                  key: "members",
                  header: "成员",
                  render: (row) => (
                    <span>
                      {displayName(row.initiator_id)} ⇄ {displayName(row.partner_id)}
                    </span>
                  ),
                },
                {
                  key: "state",
                  header: "状态",
                  render: (row) => (
                    <ConsoleTag tone={row.state === "active" ? "ok" : "default"}>
                      {row.state === "active" ? "进行中" : "已结束"}
                    </ConsoleTag>
                  ),
                },
                { key: "created", header: "开始", render: (row) => timeText(row.created_at) },
                { key: "ended", header: "结束", render: (row) => timeText(row.ended_at) },
                {
                  key: "actions",
                  header: "操作",
                  render: (row) => (
                    <span className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost"
                        onClick={() => void openPair(row.pair_id)}
                      >
                        查看消息
                      </button>
                      {row.state === "active" && (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-flare disabled:opacity-40"
                          onClick={() => void endPair(row.pair_id)}
                        >
                          结束
                        </button>
                      )}
                    </span>
                  ),
                },
              ]}
            />
          </ConsoleSection>

          {selectedPairId && (
            <ConsoleSection title={`结对会话 · ${selectedPairId}`}>
              <div className="mb-3 space-y-1.5">
                {pairMessages.length === 0 && (
                  <p className="text-xs text-mute">暂无协同消息</p>
                )}
                {pairMessages.map((item) => (
                  <div
                    key={item.message_id}
                    className="rounded border border-rail bg-hull/40 px-3 py-2 text-xs"
                  >
                    <p className="text-frost/85">{item.body}</p>
                    <p className="mt-1 text-[10px] text-mute">
                      {displayName(item.sender_id)} · {timeText(item.created_at)} ·{" "}
                      {item.delivery_status || "—"}
                    </p>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex-1 text-[11px] text-mute">
                  发送到该结对
                  <input
                    className="mt-1 block w-full rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                    value={pairBody}
                    maxLength={500}
                    disabled={!canSend}
                    placeholder="消息内容"
                    onChange={(event) => setPairBody(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="hud-btn text-xs disabled:opacity-40"
                  disabled={!canSend || !pairBody.trim()}
                  onClick={() => void sendPairMessage()}
                >
                  发送
                </button>
              </div>
              {!canSend && (
                <p className="mt-2 text-[11px] text-amber-signal">发送消息需要 message_send。</p>
              )}
            </ConsoleSection>
          )}
        </>
      )}

      {tab === "messages" && (
        <>
          <ConsoleSection title="发送结对消息">
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
                  return active
                    ? `${active.name} · ${TASK_STATE_LABEL[active.state] ?? active.state}`
                    : "—";
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
          <ConsoleSection title="登记大屏">
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-mute">
                大屏名称
                <input
                  className="mt-1 block w-48 rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={screenName}
                  disabled={!canScreen}
                  placeholder="例如：一层前台大屏"
                  onChange={(event) => setScreenName(event.target.value)}
                />
              </label>
              <label className="text-[11px] text-mute">
                初始楼层
                <select
                  className="mt-1 block rounded border border-rail bg-hull px-2 py-1.5 text-xs text-frost"
                  value={focusFloor}
                  onChange={(event) => setFocusFloor(event.target.value)}
                >
                  {(site?.floors ?? []).map((floor) => (
                    <option key={floor.floor_id} value={floor.floor_id}>
                      {floor.level}F · {floor.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="hud-btn text-xs disabled:opacity-40"
                disabled={!canScreen || busy || !screenName.trim()}
                onClick={() => void registerScreen()}
              >
                登记
              </button>
            </div>
            {!canScreen && (
              <p className="mt-2 text-[11px] text-amber-signal">
                登记与遥控大屏需要 console_admin。
              </p>
            )}
          </ConsoleSection>

          <ConsoleSection title={`大屏列表（${screens.length}）`}>
            <ConsoleTable
              rows={screens}
              rowKey={(row) => row.screen_id}
              loading={loading}
              empty="暂无已登记大屏"
              columns={[
                {
                  key: "name",
                  header: "大屏",
                  render: (row) => (
                    <span>
                      {row.name}
                      <span className="ml-2 font-mono text-[10px] text-mute">{row.screen_id}</span>
                    </span>
                  ),
                },
                { key: "floor", header: "楼层", render: (row) => row.floor_id || "—" },
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
                  key: "action",
                  header: "遥控",
                  render: (row) => (
                    <span className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={!canScreen || busy}
                        className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                        onClick={() => void focusScreen(row.screen_id)}
                      >
                        聚焦 {focusFloor || "楼层"}
                      </button>
                      <button
                        type="button"
                        disabled={!canScreen || busy || !row.online}
                        className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                        onClick={() => void leaveScreen(row.screen_id)}
                      >
                        下线
                      </button>
                    </span>
                  ),
                },
              ]}
            />
          </ConsoleSection>
        </>
      )}
    </>
  );
}
