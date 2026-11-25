import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, getToken } from "../lib/api";
import { useStaffHeartbeat } from "../lib/console-access";
import { BuildingShell } from "./BuildingShell";
import { FLOOR_GAP, FloorSlab, FloorDetailView } from "./FloorSlab";
import { SiteScene } from "./SiteScene";
import {
  floorSeats,
  seatStats,
  type OfficeSite,
  type PairBubble,
  type PairLink,
  type PublicMessage,
  type PublicTask,
  type PublicTaskNode,
  type Room,
  type Seat,
  type SeatAgent,
} from "./types";
import { useWalkers } from "./WalkerManager";
import { useScreenSync } from "./collab";
import { useCollabEvents, useStreamSignal, type StreamState } from "./stream";
import { useScreenSession } from "../lib/screen-identity";
import { usePublicConfig } from "../lib/collab/hooks";
import "./twin.css";

interface CollabPair {
  pair_id: string;
  initiator_id: string;
  partner_id: string;
  state: string;
}

interface StaffLite {
  employee_id: string;
  display_name: string;
}

const PREVIEW_QUERY_KEY = "preview";
const KIOSK_IDLE_MS = 5 * 60 * 1000; // 5 分钟无操作退回 kiosk

/** 按本地时区判定昼夜：19 点后与 6 点前视为夜晚。 */
function isNightNow(date = new Date()) {
  const hour = date.getHours();
  return hour < 6 || hour >= 19;
}

/** 夜空星点，位置固定，避免每次渲染抖动。 */
const STARS = Array.from({ length: 32 }, (_, i) => ({
  left: `${(i * 37 + 11) % 100}%`,
  top: `${((i * 53 + 7) % 58)}%`,
  size: i % 8 === 0 ? 3 : 2,
  delay: `${(i % 9) * 0.55}s`,
}));

interface Selection {
  floorId: string;
  room: Room;
  seat: Seat;
}

/** 依据视口大小缩放等距场景，保证整楼完整可见。 */
function useStageScale() {
  const [scale, setScale] = useState(0.6);
  useEffect(() => {
    const compute = () => {
      const s = Math.min(
        (window.innerWidth - 470) / 1780,
        (window.innerHeight - 160) / 2100,
      );
      setScale(Math.max(0.26, Math.min(0.8, s)));
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, []);
  return scale;
}

const STATUS_LABEL: Record<string, string> = {
  online: "在线",
  busy: "忙碌",
  offline: "离线",
};

const TASK_STATE_LABEL: Record<string, string> = {
  created: "待派发",
  dispatched: "已派发",
  running: "执行中",
  review: "评审中",
  blocked: "阻塞",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const STREAM_LABEL: Record<StreamState, string> = {
  idle: "实时待连接",
  connecting: "实时连接中",
  live: "实时",
  lost: "实时重连中",
  expired: "会话失效",
};

function timeText(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString();
}

/** 检测浏览器是否请求「弱化动画」偏好。 */
function detectReducedMotion(): boolean {
  try {
    return (
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  } catch {
    return false;
  }
}

export function TwinPage() {
  const scale = useStageScale();
  const [site, setSite] = useState<OfficeSite | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [activeFloorId, setActiveFloorId] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 });
  const [night, setNight] = useState(() => isNightNow());
  const [peek, setPeek] = useState(false);
  const [hasToken, setHasToken] = useState(() => Boolean(getToken()));

  // === 公开投影 + 权限 / kiosk ===
  const previewMode = useMemo(() => {
    try {
      if (typeof window === "undefined") return false;
      return new URLSearchParams(window.location.search).get(PREVIEW_QUERY_KEY) === "1";
    } catch {
      return false;
    }
  }, []);

  // ?kiosk=1 强制只读；未登录一律按匿名 kiosk 展示大楼。
  const [forcedKiosk] = useState<boolean>(() => {
    try {
      return (
        typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).get("kiosk") === "1"
      );
    } catch {
      return false;
    }
  });
  // 交互模式闲置超时后进入的 kiosk，只存在于内存，不写 localStorage。
  const [idleKiosk, setIdleKiosk] = useState(false);
  const isKiosk = forcedKiosk || idleKiosk || !hasToken;

  const reducedMotion = useState<boolean>(() => detectReducedMotion())[0];

  // === 5 分钟无操作退回 kiosk ===
  const kioskTimerRef = useRef<number | undefined>(undefined);
  const resetKioskTimer = useCallback(() => {
    window.clearTimeout(kioskTimerRef.current);
    kioskTimerRef.current = window.setTimeout(() => {
      setIdleKiosk(true);
      setSelection(null);
    }, KIOSK_IDLE_MS);
  }, []);

  useEffect(() => {
    if (forcedKiosk || !hasToken) return;
    const handler = () => resetKioskTimer();
    window.addEventListener("pointermove", handler);
    window.addEventListener("keydown", handler);
    window.addEventListener("wheel", handler);
    resetKioskTimer();
    return () => {
      window.clearTimeout(kioskTimerRef.current);
      window.removeEventListener("pointermove", handler);
      window.removeEventListener("keydown", handler);
      window.removeEventListener("wheel", handler);
    };
  }, [forcedKiosk, hasToken, resetKioskTimer]);

  // 公开投影 / kiosk 相关的「是否开启屏幕登记」判断：
  // - previewMode：不登记，避免产生脏数据
  // - isKiosk：匿名只读，不登记
  // - 无 token：走 public 投影，也不登记（服务端需要 Bearer 才能登记）
  const shouldRegister = !previewMode && !isKiosk && hasToken;

  // 大屏常驻时保活当前登录员工，避免超管 180 秒无心跳被置为 offline
  useStaffHeartbeat(undefined, hasToken);

  const [loadedAt, setLoadedAt] = useState("");
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const floors = useMemo(() => site?.floors ?? [], [site]);
  const shellHeight = Math.max(190, (floors.length - 1) * FLOOR_GAP + 190);
  const [pairs, setPairs] = useState<CollabPair[]>([]);
  const [staffNames, setStaffNames] = useState<Record<string, string>>({});
  const [sideTab, setSideTab] = useState<"pairs" | "roster">("pairs");
  const [rosterQuery, setRosterQuery] = useState("");
  const [rosterStatus, setRosterStatus] = useState<"all" | "online" | "busy" | "offline">("all");
  const floorsRef = useRef(floors);
  floorsRef.current = floors;
  const activeFloorRef = useRef(activeFloorId);
  activeFloorRef.current = activeFloorId;
  const seatRef = useRef(selection?.seat.seat_id ?? null);
  seatRef.current = selection?.seat.seat_id ?? null;

  /** 屏幕身份：登记 + 心跳 + 离线；preview/kiosk/无 token 时不登记。 */
  const { screenId } = useScreenSession({
    enabled: shouldRegister,
    name: "孪生大屏",
    getPayload: () => ({
      floor_id: activeFloorRef.current,
      seat_id: seatRef.current,
    }),
  });
  const screenIdRef = useRef(screenId);
  screenIdRef.current = screenId;

  /** 公开投影：config 里的 theme / resolution / layout_type / play_state / published 等白名单字段。 */
  const { data: screenConfig } = usePublicConfig(shouldRegister ? screenId : null);

  /** 布局刷新后同步已打开抽屉的工位对象，让任务进度实时更新。 */
  useEffect(() => {
    if (!selection) return;
    const floor = floors.find((item) => item.floor_id === selection.floorId);
    for (const room of floor?.rooms ?? []) {
      const seat = room.seats.find((item) => item.seat_id === selection.seat.seat_id);
      if (!seat) continue;
      if (seat !== selection.seat) {
        setSelection({ floorId: selection.floorId, room, seat });
      }
      return;
    }
  }, [floors]);

  /**
   * 真实结对 → 工位坐标。
   * 优先用公开布局自带的 pair_id / partner_name（无需登录）；
   * 旧数据没有这两个字段时，回退到结对接口 + 员工名册按姓名匹配。
   */
  const pairLinks = useMemo<PairLink[]>(() => {
    const seatById = new Map<
      string,
      { seat: Seat; room: Room; floorId: string }
    >();
    const seatByName = new Map<
      string,
      { seat: Seat; room: Room; floorId: string }
    >();
    for (const floor of floors) {
      for (const room of floor.rooms) {
        for (const seat of room.seats) {
          const entry = { seat, room, floorId: floor.floor_id };
          seatById.set(seat.seat_id, entry);
          const name = seat.agent?.display_name;
          if (name && !seatByName.has(name)) {
            seatByName.set(name, entry);
          }
        }
      }
    }

    const fromLayout: PairLink[] = [];
    const seen = new Set<string>();
    for (const entry of seatById.values()) {
      const agent = entry.seat.agent;
      if (!agent?.pair_id || !agent.partner_name || seen.has(agent.pair_id)) continue;
      const other = seatByName.get(agent.partner_name);
      if (!other) continue;
      seen.add(agent.pair_id);
      fromLayout.push({
        pair_id: agent.pair_id,
        floor_id: entry.floorId,
        same_floor: entry.floorId === other.floorId,
        a_seat_id: entry.seat.seat_id,
        b_seat_id: other.seat.seat_id,
        a_name: agent.display_name,
        b_name: agent.partner_name,
        ax: entry.seat.x,
        ay: entry.seat.y,
        bx: other.seat.x,
        by: other.seat.y,
      });
    }
    if (fromLayout.length > 0) return fromLayout;

    const links: PairLink[] = [];
    for (const pair of pairs) {
      const aName = staffNames[pair.initiator_id];
      const bName = staffNames[pair.partner_id];
      if (!aName || !bName) continue;
      const a = seatByName.get(aName);
      const b = seatByName.get(bName);
      if (!a || !b) continue;
      links.push({
        pair_id: pair.pair_id,
        floor_id: a.floorId,
        same_floor: a.floorId === b.floorId,
        a_seat_id: a.seat.seat_id,
        b_seat_id: b.seat.seat_id,
        a_name: aName,
        b_name: bName,
        ax: a.seat.x,
        ay: a.seat.y,
        bx: b.seat.x,
        by: b.seat.y,
      });
    }
    return links;
  }, [floors, pairs, staffNames]);

  /** 侧栏结对行：同样优先公开布局，回退到接口 + 名册。 */
  const pairRows = useMemo(() => {
    const fromLayout: { pair_id: string; a_name: string; b_name: string }[] = [];
    const seen = new Set<string>();
    for (const floor of floors) {
      for (const room of floor.rooms) {
        for (const seat of room.seats) {
          const agent = seat.agent;
          if (!agent?.pair_id || !agent.partner_name || seen.has(agent.pair_id)) {
            continue;
          }
          seen.add(agent.pair_id);
          fromLayout.push({
            pair_id: agent.pair_id,
            a_name: agent.display_name,
            b_name: agent.partner_name,
          });
        }
      }
    }
    if (fromLayout.length > 0) return fromLayout;
    return pairs.map((pair) => ({
      pair_id: pair.pair_id,
      a_name: staffNames[pair.initiator_id] ?? pair.initiator_id,
      b_name: staffNames[pair.partner_id] ?? pair.partner_id,
    }));
  }, [floors, pairs, staffNames]);

  /** 同层真实结对：交给 WalkerManager，让两人结伴走向会议室/休息区。 */
  const realPairs = useMemo(
    () =>
      pairLinks
        .filter((link) => link.same_floor)
        .map((link) => ({
          pairId: link.pair_id,
          aSeatId: link.a_seat_id,
          bSeatId: link.b_seat_id,
        })),
    [pairLinks],
  );

  const pairLinkById = useMemo(() => {
    const map = new Map<string, PairLink>();
    for (const link of pairLinks) map.set(link.pair_id, link);
    return map;
  }, [pairLinks]);

  /** 每个结对最近 3 条公开消息（已脱敏）。 */
  const [pairMessages, setPairMessages] = useState<Record<string, PublicMessage[]>>({});

  /** 首次进入或结对集合变化时拉一次快照；后续增量由 message.created 事件驱动。 */
  const refreshMessages = useCallback(async (ids: string[]) => {
    if (ids.length === 0) {
      setPairMessages({});
      return;
    }
    const entries = await Promise.all(
      ids.map(async (id) => {
        const result = await api<PublicMessage[]>(
          `/api/public/collab/messages?pair_id=${encodeURIComponent(id)}&limit=3`,
        );
        return [id, result.ok && Array.isArray(result.data) ? result.data : []] as const;
      }),
    );
    setPairMessages((prev) => {
      const next: Record<string, PublicMessage[]> = {};
      for (const [id, list] of entries) {
        // 事件可能先于快照到达，保留快照里没有的更新消息，避免被覆盖。
        const seen = new Set(list.map((message) => message.message_id));
        const fresh = (prev[id] ?? []).filter((message) => !seen.has(message.message_id));
        next[id] = [...fresh, ...list].slice(0, 3);
      }
      return next;
    });
  }, []);

  const pairIdsKey = pairRows.map((row) => row.pair_id).join(",");
  useEffect(() => {
    if (!pairIdsKey) {
      setPairMessages({});
      return;
    }
    void refreshMessages(pairIdsKey.split(","));
  }, [pairIdsKey, refreshMessages]);

  /** 实时消息事件：把新消息插入对应结对，最多保留 3 条。 */
  const applyMessageEvent = useCallback((raw: string) => {
    try {
      const payload = JSON.parse(raw) as {
        message_id?: string;
        pair_id?: string | null;
        kind?: string;
        body?: string;
        created_at?: string | null;
      };
      if (!payload.message_id || !payload.pair_id || typeof payload.body !== "string") return;
      const pairId = payload.pair_id;
      const incoming: PublicMessage = {
        message_id: payload.message_id,
        kind: payload.kind ?? "note",
        body: payload.body,
        created_at: payload.created_at ?? null,
        delivery_status: null,
        pair_id: pairId,
      };
      setPairMessages((prev) => {
        const list = prev[pairId] ?? [];
        if (list.some((message) => message.message_id === incoming.message_id)) return prev;
        return { ...prev, [pairId]: [incoming, ...list].slice(0, 3) };
      });
    } catch {
      // 坏帧忽略，不影响后续事件
    }
  }, []);

  /** 任务变化时让对应工位脉冲提示，2.6 秒后自动消失。 */
  const [pulseSeatId, setPulseSeatId] = useState<string | null>(null);
  const pulseTimerRef = useRef<number | undefined>(undefined);

  const pulseSeat = useCallback((seatId: string) => {
    if (!seatId) return;
    setPulseSeatId(seatId);
    window.clearTimeout(pulseTimerRef.current);
    pulseTimerRef.current = window.setTimeout(() => setPulseSeatId(null), 2_600);
  }, []);

  useEffect(() => () => window.clearTimeout(pulseTimerRef.current), []);

  /** 公开任务详情：抽屉打开时按 task_id 拉取节点时间线。 */
  const [taskNodes, setTaskNodes] = useState<Record<string, PublicTaskNode[]>>({});

  const refreshTaskDetail = useCallback(async (taskId: string) => {
    const result = await api<PublicTask>(
      `/api/public/collab/tasks/${encodeURIComponent(taskId)}`,
    );
    if (result.ok && result.data && Array.isArray(result.data.nodes)) {
      const nodes = result.data.nodes;
      setTaskNodes((prev) => ({ ...prev, [taskId]: nodes }));
    }
  }, []);

  /** 抽屉内的员工任务列表：按 seat_id 由后端解析员工，公开投影不含身份字段。 */
  const [seatTasks, setSeatTasks] = useState<PublicTask[]>([]);
  const [seatTasksLoading, setSeatTasksLoading] = useState(false);
  const [openTaskId, setOpenTaskId] = useState<string | null>(null);

  const refreshSeatTasks = useCallback(async (seatId: string) => {
    setSeatTasksLoading(true);
    const result = await api<PublicTask[]>(
      `/api/public/collab/seats/${encodeURIComponent(seatId)}/tasks`,
    );
    setSeatTasksLoading(false);
    setSeatTasks(result.ok && Array.isArray(result.data) ? result.data : []);
  }, []);

  const selectedSeatId = selection?.seat.seat_id ?? null;
  const selectionRef = useRef(selection);
  useEffect(() => {
    selectionRef.current = selection;
  }, [selection]);

  // 公开 SSE 的 task.updated 已脱敏（不含 task_id），抽屉节点时间线改用本地已知的打开任务刷新
  const openTaskIdRef = useRef(openTaskId);
  useEffect(() => {
    openTaskIdRef.current = openTaskId;
  }, [openTaskId]);

  useEffect(() => {
    setOpenTaskId(null);
    setSeatTasks([]);
    if (selectedSeatId) void refreshSeatTasks(selectedSeatId);
  }, [selectedSeatId, refreshSeatTasks]);

  const activeTaskId = openTaskId ?? selection?.seat.agent?.task_id ?? null;
  useEffect(() => {
    if (activeTaskId) void refreshTaskDetail(activeTaskId);
  }, [activeTaskId, refreshTaskDetail]);

  const drawerTaskNodes = taskNodes[activeTaskId ?? ""] ?? [];

  /** 消息气泡：每个同层结对取最新一条，锚定在连线中点。 */
  const pairBubbles = useMemo<PairBubble[]>(() => {
    const bubbles: PairBubble[] = [];
    for (const link of pairLinks) {
      if (!link.same_floor) continue;
      const latest = pairMessages[link.pair_id]?.[0];
      if (!latest) continue;
      bubbles.push({
        pair_id: link.pair_id,
        floor_id: link.floor_id,
        message_id: latest.message_id,
        body: latest.body,
        created_at: latest.created_at,
        x: (link.ax + link.bx) / 2,
        y: (link.ay + link.by) / 2,
      });
    }
    return bubbles;
  }, [pairLinks, pairMessages]);

  /** 全量花名册：按姓名排序（公开布局已含座席上的员工）。 */
  const rosterAll = useMemo(() => {
    const list: Array<{
      floorId: string;
      level: number;
      room: Room;
      seat: Seat;
      agent: SeatAgent;
    }> = [];
    for (const floor of floors) {
      for (const room of floor.rooms) {
        for (const seat of room.seats) {
          if (!seat.agent) continue;
          list.push({
            floorId: floor.floor_id,
            level: floor.level,
            room,
            seat,
            agent: seat.agent,
          });
        }
      }
    }
    return list.sort((a, b) =>
      a.agent.display_name.localeCompare(b.agent.display_name, "zh-Hans-CN"),
    );
  }, [floors]);

  /** 花名册过滤：姓名 / Agent / 团队 / 职位 / 工位号 + 状态。 */
  const rosterFiltered = useMemo(() => {
    const keyword = rosterQuery.trim().toLowerCase();
    return rosterAll.filter((person) => {
      if (rosterStatus !== "all" && person.agent.status !== rosterStatus) return false;
      if (!keyword) return true;
      return [
        person.agent.display_name,
        person.agent.agent_name ?? "",
        person.agent.team ?? "",
        person.agent.position,
        person.seat.seat_id,
      ].some((value) => value.toLowerCase().includes(keyword));
    });
  }, [rosterAll, rosterQuery, rosterStatus]);

  const activeFloor = activeFloorId
    ? floors.find((f) => f.floor_id === activeFloorId) ?? null
    : null;
  // 只为当前查看的楼层派活动，避免并发名额被其它楼层分摊
  const walkerFloors = useMemo(() => (activeFloor ? [activeFloor] : []), [activeFloor]);

  /** Walker 活动：仅在 focused 模式下启用，避免 overview 渲染/走路太多 DOM。 */
  const { routes: walkerRoutes, removeRoute } = useWalkers(walkerFloors, {
    maxConcurrent: 3,
    tickMs: 2400,
    enabled: !!activeFloorId && !reducedMotion,
    realPairs,
  });

  /** 布局读取：进行中的请求合并，多次快照只保留一次在途刷新。 */
  const aliveRef = useRef(true);
  const inFlightRef = useRef(false);
  const queuedRef = useRef(false);
  const refreshLayout = useCallback(async () => {
    if (inFlightRef.current) {
      queuedRef.current = true;
      return;
    }
    inFlightRef.current = true;
    do {
      queuedRef.current = false;
      const result = await api<OfficeSite>("/api/public/layout");
      if (!aliveRef.current) break;
      if (result.ok) {
        setSite(result.data);
        setLoadFailed(false);
        setLoadedAt(new Date().toISOString());
      } else {
        setLoadFailed(true);
      }
    } while (queuedRef.current);
    inFlightRef.current = false;
  }, []);

  /** 结对与员工名册：事件到达时刷新，不用轮询。 */
  const refreshPairs = useCallback(async () => {
    const [pairRes, staffRes] = await Promise.all([
      api<CollabPair[]>("/api/collab/pairs?state=active"),
      api<StaffLite[]>("/api/identity/staff?status=all"),
    ]);
    if (pairRes.ok && Array.isArray(pairRes.data)) setPairs(pairRes.data);
    if (staffRes.ok && Array.isArray(staffRes.data)) {
      const map: Record<string, string> = {};
      for (const person of staffRes.data) map[person.employee_id] = person.display_name;
      setStaffNames(map);
    }
  }, []);

  /** 遥控聚焦：只接受本大屏 screen_id 的 screen.focus。 */
  const applyRemoteFocus = useCallback((floorId: string, seatId?: string | null) => {
    setActiveFloorId(floorId);
    setPeek(false);
    setView({ zoom: 1, panX: 0, panY: 0 });
    if (!seatId) {
      setSelection(null);
      return;
    }
    for (const floor of floorsRef.current) {
      for (const room of floor.rooms) {
        const seat = room.seats.find((item) => item.seat_id === seatId);
        if (seat) {
          setSelection({ floorId: floor.floor_id, room, seat });
          return;
        }
      }
    }
    setSelection(null);
  }, []);

  /** 登录态变化：管理中心登录/退出后同步大屏门槛。 */
  useEffect(() => {
    const sync = () => setHasToken(Boolean(getToken()));
    window.addEventListener("mailbus:auth-ok", sync);
    window.addEventListener("mailbus:auth-required", sync);
    const onStorage = (event: StorageEvent) => {
      if (event.key === "mailbus_api_token") sync();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("mailbus:auth-ok", sync);
      window.removeEventListener("mailbus:auth-required", sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  /** 登录后实时信号：SSE 只作为「布局可能变化」的提示，不推导布局数据。 */
  const stream = useStreamSignal({
    enabled: hasToken,
    onSnapshot: () => void refreshLayout(),
  });

  /** 协同增量事件：pair.* 刷新结对，message.created 实时插入气泡，screen.focus 驱动本屏聚焦。 */
  const collabStream = useCollabEvents({
    enabled: true,
    url: "/api/public/collab/stream",
    screenId: screenId,
    onEvent: (event) => {
      if (event.event === "message.created") {
        applyMessageEvent(event.data);
        return;
      }
      if (event.event === "task.updated") {
        try {
          const payload = JSON.parse(event.data) as { seat_id?: string };
          if (payload.seat_id) {
            pulseSeat(payload.seat_id);
            if (payload.seat_id === selectionRef.current?.seat.seat_id) {
              void refreshSeatTasks(payload.seat_id);
              if (openTaskIdRef.current) {
                void refreshTaskDetail(openTaskIdRef.current);
              }
            }
          }
        } catch {
          // 坏帧只影响脉冲提示，仍然刷新布局
        }
        void refreshLayout();
        return;
      }
      if (event.event.startsWith("pair.")) {
        void refreshPairs();
        void refreshLayout();
      }
      if (event.event !== "screen.focus") return;
      try {
        const payload = JSON.parse(event.data) as {
          screen_id?: string;
          floor_id?: string | null;
          seat_id?: string | null;
        };
        if (payload.screen_id !== screenIdRef.current || !payload.floor_id) return;
        applyRemoteFocus(payload.floor_id, payload.seat_id ?? null);
      } catch {
        // 坏帧忽略，不影响后续事件
      }
    },
  });

  /** 断线重连后补拉一次快照，避免错过断线期间的消息（事件流无重放）。 */
  useEffect(() => {
    if (collabStream !== "live" || !pairIdsKey) return;
    void refreshMessages(pairIdsKey.split(","));
  }, [collabStream, pairIdsKey, refreshMessages]);

  /** 结对名册：进入页面、恢复可见时刷新；后续由 collab 事件驱动。 */
  useEffect(() => {
    if (!hasToken) return;
    void refreshPairs();
    const onVisibility = () => {
      if (!document.hidden) void refreshPairs();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [hasToken, refreshPairs]);

  useEffect(() => {
    aliveRef.current = true;
    void refreshLayout();
    const onVisibility = () => {
      if (!document.hidden) void refreshLayout();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      aliveRef.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshLayout]);

  /** 多端同步：其它大屏切换楼层/员工时本屏跟随（带防回环标记）。 */
  const remoteRef = useRef<boolean | null>(null);
  const { peers, sendView } = useScreenSync((view) => {
    remoteRef.current = true;
    setActiveFloorId(view.floorId);
    if (!view.seatId) {
      setSelection(null);
      return;
    }
    for (const floor of floors) {
      for (const room of floor.rooms) {
        const seat = room.seats.find((s) => s.seat_id === view.seatId);
        if (seat) {
          setSelection({ floorId: floor.floor_id, room, seat });
          return;
        }
      }
    }
    setSelection(null);
  });

  useEffect(() => {
    // 首次挂载不回播，避免新开一块大屏把已有大屏拉回整楼
    if (remoteRef.current === null) {
      remoteRef.current = false;
      return;
    }
    if (remoteRef.current) {
      remoteRef.current = false;
      return;
    }
    sendView({ floorId: activeFloorId, seatId: selection?.seat.seat_id ?? null });
  }, [activeFloorId, selection?.seat.seat_id, sendView]);

  /** 本地时间每分钟刷新一次，自动跨过昼夜分界。 */
  useEffect(() => {
    const timer = window.setInterval(() => setNight(isNightNow()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  // ESC 退出 detail 模式
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && activeFloorId) {
        setActiveFloorId(null);
        setSelection(null);
        setPeek(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeFloorId]);

  /** 根据光标是否在大楼投影范围内双向控制 peek 状态。
   *  每次 pointermove 都做显式边界检测，overview 和 focused 模式均生效：
   *  - 在大楼内 → peek=true（露出楼层）
   *  - 在大楼外 → peek=false（外壳关闭）
   *  仅排除拖拽状态。focused 模式下 peek 独立控制外壳显隐。 */
  const updatePeekFromPointer = (clientX: number, clientY: number) => {
    if (dragRef.current) return;
    const box = stageRef.current?.querySelector<HTMLElement>(".building");
    if (!box) return;
    const rect = box.getBoundingClientRect();
    const rise = shellHeight * scale * view.zoom * 0.7;
    const pad = 40;
    const inside =
      clientX >= rect.left - pad &&
      clientX <= rect.right + pad &&
      clientY >= rect.top - rise - pad &&
      clientY <= rect.bottom + pad;
    setPeek((prev) => (prev === inside ? prev : inside));
  };

  const totals = useMemo(() => {
    const all = floors.flatMap(floorSeats);
    return {
      total: all.length,
      online: all.filter((s) => s.agent?.status === "online").length,
      busy: all.filter((s) => s.agent?.status === "busy").length,
      offline: all.filter((s) => s.agent?.status === "offline").length,
      empty: all.filter((s) => !s.agent).length,
    };
  }, [floors]);

  const activeIndex = useMemo(() => {
    if (!activeFloorId) return null;
    return floors.findIndex((f) => f.floor_id === activeFloorId);
  }, [activeFloorId, floors]);

  /** 点哪层进哪层：直接聚焦，不再切换回整楼。 */
  const enterFloor = (floorId: string) => {
    setActiveFloorId(floorId);
    setSelection(null);
    setPeek(false);
    setView({ zoom: 1, panX: 0, panY: 0 });
  };

  const locateSeat = () => {
    if (!selection) return;
    setActiveFloorId(selection.floorId);
  };

  /** 定位到某个工位：进入所在楼层、居中复位并打开详情抽屉。 */
  const focusSeat = (floorId: string, room: Room, seat: Seat) => {
    setActiveFloorId(floorId);
    setPeek(false);
    setView({ zoom: 1, panX: 0, panY: 0 });
    setSelection({ floorId, room, seat });
  };

  /** 点击侧栏结对：定位到发起人所在楼层并打开其详情抽屉。 */
  const focusPair = (link: PairLink) => {
    for (const floor of floors) {
      for (const room of floor.rooms) {
        const seat = room.seats.find((s) => s.seat_id === link.a_seat_id);
        if (seat) {
          focusSeat(floor.floor_id, room, seat);
          return;
        }
      }
    }
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const next = Math.min(2.6, Math.max(0.65, view.zoom * Math.exp(-e.deltaY * 0.0012)));
    setView((v) => ({ ...v, zoom: next }));
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    dragRef.current = { x: e.clientX, y: e.clientY, panX: view.panX, panY: view.panY };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    updatePeekFromPointer(e.clientX, e.clientY);
    const drag = dragRef.current;
    if (!drag) return;
    setView((v) => ({
      ...v,
      panX: drag.panX + (e.clientX - drag.x),
      panY: drag.panY + (e.clientY - drag.y),
    }));
  };

  const endDrag = () => {
    dragRef.current = null;
  };

  const centerIndex = activeIndex ?? Math.floor((floors.length - 1) / 2);
  const sceneScale = scale * view.zoom * (activeIndex !== null ? 1.32 : 1);
  const centerZ = activeIndex !== null ? centerIndex * FLOOR_GAP : shellHeight / 2;

  const rootClass = [
    "twin-root",
    activeFloorId ? "is-detail" : "is-overview",
    night ? "is-night" : "is-day",
    peek ? "is-peek" : "",
    reducedMotion ? "is-reduced-motion" : "",
    isKiosk ? "is-kiosk" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={rootClass}>
      <header className="twin-header">
        <div className="twin-brand">
          <span className="brand-mark">◈</span>
          <div>
            <h1>Ziyan办公大楼</h1>
            <p>
              {site ? `${site.org_name} · ${site.name}` : "等待布局数据"}
              {screenConfig
                ? ` · v${screenConfig.config_version} · ${screenConfig.theme}/${screenConfig.resolution}`
                : ""}
            </p>
          </div>
        </div>
        {activeFloor ? (
          <div className="twin-detail-meta">
            <button
              type="button"
              className="btn-back"
              onClick={() => {
                setActiveFloorId(null);
                setSelection(null);
                setPeek(false);
              }}
            >
              ← 返回整楼
            </button>
            <span className="detail-title">
              <strong>{activeFloor.level}F</strong> · {activeFloor.name}
            </span>
            <span className="detail-stats">
              在线 {seatStats(activeFloor).online} · 空位 {seatStats(activeFloor).empty}
              {loadFailed ? " · 数据不可用" : ""}
            </span>
          </div>
        ) : (
          <div className="twin-metrics">
            <span className="metric"><i className="dot dot-online" />在线 {totals.online}</span>
            <span className="metric"><i className="dot dot-busy" />忙碌 {totals.busy}</span>
            <span className="metric"><i className="dot dot-offline" />离线 {totals.offline}</span>
            <span className="metric"><i className="dot dot-busy" />结对 {pairRows.length}</span>
            <span className="metric"><i className="dot dot-online" />协同 {peers + 1} 屏</span>
            <span className={`metric metric-stream status-${stream.state}`}>
              {STREAM_LABEL[stream.state]}
              {loadedAt ? ` · ${timeText(loadedAt)}` : ""}
            </span>
            <span className={`metric metric-clock${night ? " is-night" : ""}`}>
              {night ? "夜间" : "日间"}
            </span>
            <span className="metric metric-ghost">空位 {totals.empty} / 工位 {totals.total}</span>
            {previewMode && <span className="metric metric-ghost">preview</span>}
            {loadFailed && <span className="metric metric-ghost">数据不可用</span>}
          </div>
        )}
        {isKiosk && hasToken && !forcedKiosk ? (
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setIdleKiosk(false);
              resetKioskTimer();
            }}
          >
            进入交互模式
          </button>
        ) : null}
      </header>

      <div className="twin-body">
        {!isKiosk && (
        <aside className="collab-pairs">
          <div className="side-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "pairs"}
              className={sideTab === "pairs" ? "is-active" : undefined}
              onClick={() => setSideTab("pairs")}
            >
              协同结对 <span>{pairs.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "roster"}
              className={sideTab === "roster" ? "is-active" : undefined}
              onClick={() => setSideTab("roster")}
            >
              员工 <span>{rosterAll.length}</span>
            </button>
          </div>
          {sideTab === "pairs" ? (
            <>
              {pairRows.length === 0 ? (
                <p className="collab-pairs-empty">暂无进行中的结对</p>
              ) : (
                <ul>
                  {pairRows.map((row) => {
                    const link = pairLinkById.get(row.pair_id);
                    return (
                      <li
                        key={row.pair_id}
                        className={link ? "is-clickable" : undefined}
                        onClick={link ? () => focusPair(link) : undefined}
                        onKeyDown={
                          link
                            ? (e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  focusPair(link);
                                }
                              }
                            : undefined
                        }
                        role={link ? "button" : undefined}
                        tabIndex={link ? 0 : undefined}
                        title={link ? "点击定位到该结对" : undefined}
                      >
                        <span>{row.a_name}</span>
                        <i>⇄</i>
                        <span>{row.b_name}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          ) : (
            <div className="roster">
              <input
                className="roster-search"
                type="search"
                value={rosterQuery}
                onChange={(e) => setRosterQuery(e.target.value)}
                placeholder="搜索姓名 / Agent / 团队"
                aria-label="搜索员工"
              />
              <div className="roster-filters" role="group" aria-label="按状态筛选">
                {(
                  [
                    ["all", "全部"],
                    ["online", "在线"],
                    ["busy", "忙碌"],
                    ["offline", "离线"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className={rosterStatus === key ? "is-active" : undefined}
                    onClick={() => setRosterStatus(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {rosterFiltered.length === 0 ? (
                <p className="collab-pairs-empty">没有匹配的员工</p>
              ) : (
                <ul className="roster-list">
                  {rosterFiltered.map((person) => (
                    <li
                      key={person.seat.seat_id}
                      className="roster-row is-clickable"
                      onClick={() => focusSeat(person.floorId, person.room, person.seat)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          focusSeat(person.floorId, person.room, person.seat);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      title={`点击定位到 ${person.agent.display_name}`}
                    >
                      <i className={`dot dot-${person.agent.status}`} />
                      <span className="roster-name">{person.agent.display_name}</span>
                      <span className="roster-where">
                        {person.level}F · {person.room.name}
                      </span>
                      <span className={`roster-state status-text status-${person.agent.status}`}>
                        {STATUS_LABEL[person.agent.status]}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <p className="collab-pairs-hint">
            协同流：{STREAM_LABEL[collabStream]} · 本屏 {screenIdRef.current}
          </p>
        </aside>
        )}

        {!site ? (
          <div
            className="twin-stage"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
            }}
          >
            <p className="mono">{loadFailed ? "布局数据不可用" : "正在加载布局…"}</p>
            {!isKiosk && (
              <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>
                首次读取 GET /api/public/layout · 之后由 /api/stream 变更信号触发刷新
              </p>
            )}
          </div>
        ) : activeFloor ? (
          // ── detail 模式：全屏独立办公室 2D 画面 ──────────
          <FloorDetailView
            floor={activeFloor}
            selection={selection}
            walkerRoutes={walkerRoutes}
            pairLinks={pairLinks.filter((link) => link.floor_id === activeFloor.floor_id)}
            pairBubbles={pairBubbles.filter((bubble) => bubble.floor_id === activeFloor.floor_id)}
            pulseSeatId={pulseSeatId}
            onWalkerArrive={removeRoute}
            onSelectSeat={(seat, room) => {
              if (isKiosk || !seat.agent) return;
              setSelection({ floorId: activeFloor.floor_id, room, seat });
            }}
          />
        ) : (
          // ── overview 模式：3D 大楼场景 ────────────────────
          <div
            className="twin-stage"
            ref={stageRef}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerLeave={() => {
              endDrag();
              setPeek(false);
            }}
            onDoubleClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}
          >
            <div className="sky">
              <span className="sun" />
              <span className="sun-ring" />
              <span className="moon" />
              <div className="stars">
                {STARS.map((star, i) => (
                  <span
                    key={`star-${i}`}
                    className="star"
                    style={{
                      left: star.left,
                      top: star.top,
                      width: star.size,
                      height: star.size,
                      animationDelay: star.delay,
                    }}
                  />
                ))}
              </div>
              <span className="cloud c1" />
              <span className="cloud c2" />
              <span className="cloud c3" />
            </div>
            <div className="twin-scene">
              <div
                className="scene-scale"
                style={{
                  transform: `translate(${view.panX}px, ${view.panY}px) scale(${sceneScale})`,
                }}
              >
                <div
                  className="building"
                  style={{
                    transform: `rotateX(54deg) rotateZ(-42deg) translateZ(${-centerZ}px)`,
                  }}
                >
                  <SiteScene visible={!activeFloorId} />
                  <div className="building-core">
                    <BuildingShell height={shellHeight} detail={peek} />
                    {(peek) && floors.map((floor, index) => {
                      const floorSeatIds = new Set(
                        floor.rooms.flatMap((r) => r.seats.map((s) => s.seat_id)),
                      );
                      const floorWalkers = walkerRoutes.filter((route) => floorSeatIds.has(route.seatId));
                      return (
                        <FloorSlab
                          key={floor.floor_id}
                          floor={floor}
                          index={index}
                          active={false}
                          dimmed={false}
                          selectedSeatId={selection?.seat.seat_id ?? null}
                          walkerRoutes={floorWalkers}
                          pairLinks={pairLinks.filter((link) => link.floor_id === floor.floor_id)}
                          pairBubbles={pairBubbles.filter((bubble) => bubble.floor_id === floor.floor_id)}
                          pulseSeatId={pulseSeatId}
                          onWalkerArrive={removeRoute}
                          onSelectFloor={enterFloor}
                          onSelectSeat={(seat, room) => {
                            if (isKiosk || !seat.agent) return;
                            setSelection({ floorId: floor.floor_id, room, seat });
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {site && (
          <aside className="floor-tabs">
            <button
              type="button"
              className={`floor-tab${activeFloorId === null ? " is-active" : ""}`}
              onClick={() => {
                setActiveFloorId(null);
                setSelection(null);
                setPeek(false);
              }}
            >
              <span className="tab-title">整楼剖视</span>
              <span className="tab-meta">全部 {floors.length} 层</span>
            </button>
            {floors.map((floor) => {
              const stats = seatStats(floor);
              return (
                <button
                  key={floor.floor_id}
                  type="button"
                  className={`floor-tab${activeFloorId === floor.floor_id ? " is-active" : ""}`}
                  onClick={() => enterFloor(floor.floor_id)}
                >
                  <span className="tab-level">{floor.level}F</span>
                  <span className="tab-title">{floor.name.split(" · ")[1]}</span>
                  <span className="tab-meta">
                    <i className="dot dot-online" />{stats.online}
                    <i className="dot dot-empty" />{stats.empty}
                  </span>
                </button>
              );
            })}
          </aside>
        )}

        {selection && !isKiosk ? (
          <aside className="seat-drawer">
            <div className="drawer-head">
              <span className={`drawer-avatar status-${selection.seat.agent?.status}`}>
                {selection.seat.agent?.display_name.slice(0, 1)}
              </span>
              <div>
                <strong>{selection.seat.agent?.display_name}</strong>
                <p>
                  {[selection.seat.agent?.position, selection.seat.agent?.team]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <button type="button" className="drawer-close" onClick={() => setSelection(null)}>
                ✕
              </button>
            </div>
            <dl className="drawer-list">
              <div>
                <dt>Agent</dt>
                <dd>
                  {selection.seat.agent?.agent_name || "—"}
                  {selection.seat.agent?.agent_framework ? (
                    <span className="drawer-agent-tag">
                      {selection.seat.agent.agent_framework}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd className={`status-text status-${selection.seat.agent?.status}`}>
                  {STATUS_LABEL[selection.seat.agent?.status ?? "offline"]}
                </dd>
              </div>
              <div>
                <dt>当前任务</dt>
                <dd>
                  {selection.seat.agent?.task || "—"}
                  {selection.seat.agent?.task_state ? (
                    <span className="drawer-task-state">
                      {TASK_STATE_LABEL[selection.seat.agent.task_state] ??
                        selection.seat.agent.task_state}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>任务节点</dt>
                <dd>
                  {selection.seat.agent?.current_node || "—"}
                  {selection.seat.agent?.node_state ? (
                    <span className="drawer-node-state">
                      {TASK_STATE_LABEL[selection.seat.agent.node_state] ??
                        selection.seat.agent.node_state}
                    </span>
                  ) : null}
                </dd>
              </div>
              {(selection.seat.agent?.progress_total ?? 0) > 0 ? (
                <div>
                  <dt>执行进度</dt>
                  <dd className="drawer-progress-cell">
                    <span className="drawer-progress">
                      <i
                        style={{
                          width: `${Math.min(
                            100,
                            Math.round(
                              ((selection.seat.agent?.progress_done ?? 0) /
                                (selection.seat.agent?.progress_total ?? 1)) *
                                100,
                            ),
                          )}%`,
                        }}
                      />
                    </span>
                    <span className="mono">
                      {selection.seat.agent?.progress_done ?? 0}/
                      {selection.seat.agent?.progress_total}
                    </span>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>任务列表</dt>
                <dd>
                  {seatTasksLoading ? (
                    <span className="drawer-task-empty">加载中…</span>
                  ) : seatTasks.length === 0 ? (
                    <span className="drawer-task-empty">暂无任务</span>
                  ) : (
                    <ul className="drawer-task-list">
                      {seatTasks.map((task) => (
                        <li key={task.task_id}>
                          <button
                            type="button"
                            className={`drawer-task-item${
                              activeTaskId === task.task_id ? " is-active" : ""
                            }`}
                            onClick={() => {
                              setOpenTaskId(task.task_id);
                              void refreshTaskDetail(task.task_id);
                            }}
                          >
                            <span>{task.title}</span>
                            <em>{TASK_STATE_LABEL[task.state] ?? task.state}</em>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
              {drawerTaskNodes.length > 0 ? (
                <div>
                  <dt>节点时间线</dt>
                  <dd>
                    <ol className="drawer-nodes">
                      {drawerTaskNodes.map((node, index) => (
                        <li
                          key={`${node.order}-${index}`}
                          className={`drawer-node is-${node.state}`}
                        >
                          <i />
                          <span>{node.name}</span>
                        </li>
                      ))}
                    </ol>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>所在位置</dt>
                <dd>
                  {floors.find((f) => f.floor_id === selection.floorId)?.level}F ·{" "}
                  {selection.room.name} · {selection.seat.seat_id}
                </dd>
              </div>
            </dl>
            <div className="drawer-actions">
              <button type="button" className="btn-primary" onClick={locateSeat}>
                聚焦该楼层
              </button>
              <button type="button" className="btn-ghost" onClick={() => setSelection(null)}>
                关闭
              </button>
            </div>
          </aside>
        ) : null}
      </div>

      <footer className="twin-footer">
        <span>悬停大楼展开楼层 · 点击楼层聚焦 · 点击员工查看详情 · 滚轮缩放 / 拖拽平移 · 双击复位</span>
        {isKiosk ? (
          <span className="mono">
            {loadFailed ? "上次数据可能过期" : ""}
            {previewMode ? " · preview" : ""}
          </span>
        ) : (
          <span className="mono">
            实时信号 /api/stream · 协同 /api/public/collab/stream · 布局 /api/public/layout
            {loadFailed ? " · 上次数据可能过期" : ""}
            {previewMode ? " · preview" : ""}
          </span>
        )}
      </footer>
    </div>
  );
}
