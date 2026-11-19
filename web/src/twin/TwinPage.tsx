import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, getToken } from "../lib/api";
import { BuildingShell } from "./BuildingShell";
import { FLOOR_GAP, FloorSlab, FloorDetailView } from "./FloorSlab";
import { SiteScene } from "./SiteScene";
import { floorSeats, seatStats } from "./types";
import { useWalkers } from "./WalkerManager";
import { useScreenSync } from "./collab";
import { useStreamSignal, type StreamState } from "./stream";
import type { OfficeSite, Room, Seat } from "./types";
import "./twin.css";

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
  const [loadedAt, setLoadedAt] = useState("");
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const floors = useMemo(() => site?.floors ?? [], [site]);
  const shellHeight = Math.max(190, (floors.length - 1) * FLOOR_GAP + 190);

  const activeFloor = activeFloorId
    ? floors.find((f) => f.floor_id === activeFloorId) ?? null
    : null;
  // 只为当前查看的楼层派活动，避免并发名额被其它楼层分摊
  const walkerFloors = useMemo(() => (activeFloor ? [activeFloor] : []), [activeFloor]);

  /** Walker 活动：仅在 focused 模式下启用，避免 overview 渲染/走路太多 DOM。 */
  const { routes: walkerRoutes, removeRoute } = useWalkers(walkerFloors, {
    maxConcurrent: 8,
    tickMs: 1300,
    enabled: !!activeFloorId,
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

  useEffect(() => {
    aliveRef.current = true;
    if (hasToken) void refreshLayout();
    const onVisibility = () => {
      if (!document.hidden && hasToken) void refreshLayout();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      aliveRef.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [hasToken, refreshLayout]);

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

  if (!hasToken) {
    return (
      <div className="twin-root is-day">
        <header className="twin-header">
          <div className="twin-brand">
            <span className="brand-mark">◈</span>
            <div>
              <h1>Ziyan办公大楼</h1>
              <p>需要登录后查看实时大屏</p>
            </div>
          </div>
        </header>
        <div className="twin-body">
          <div
            className="twin-stage"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 10,
            }}
          >
            <p className="mono">登录后查看实时大屏</p>
            <p
              className="mono"
              style={{ fontSize: 12, opacity: 0.7, maxWidth: 460, textAlign: "center" }}
            >
              大屏使用登录态 Bearer 连接 /api/stream，仅在业务变化时刷新公开布局。
            </p>
            <a className="btn-primary" href="/console">
              前往管理中心登录
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`twin-root${activeFloorId ? " is-detail" : " is-overview"}${
        night ? " is-night" : " is-day"
      }${peek ? " is-peek" : ""}`}
    >
      <header className="twin-header">
        <div className="twin-brand">
          <span className="brand-mark">◈</span>
          <div>
            <h1>Ziyan办公大楼</h1>
            <p>{site ? `${site.org_name} · ${site.name}` : "等待布局数据"}</p>
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
            <span className="metric"><i className="dot dot-online" />协同 {peers + 1} 屏</span>
            <span className={`metric metric-stream status-${stream.state}`}>
              {STREAM_LABEL[stream.state]}
              {loadedAt ? ` · ${timeText(loadedAt)}` : ""}
            </span>
            <span className={`metric metric-clock${night ? " is-night" : ""}`}>
              {night ? "夜间" : "日间"}
            </span>
            <span className="metric metric-ghost">空位 {totals.empty} / 工位 {totals.total}</span>
            {loadFailed && <span className="metric metric-ghost">数据不可用</span>}
          </div>
        )}
      </header>

      <div className="twin-body">
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
            <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>
              首次读取 GET /api/public/layout · 之后由 /api/stream 变更信号触发刷新
            </p>
          </div>
        ) : activeFloor ? (
          // ── detail 模式：全屏独立办公室 2D 画面 ──────────
          <FloorDetailView
            floor={activeFloor}
            selection={selection}
            walkerRoutes={walkerRoutes}
            onWalkerArrive={removeRoute}
            onSelectSeat={(seat, room) => {
              if (!seat.agent) return;
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
                          onWalkerArrive={removeRoute}
                          onSelectFloor={enterFloor}
                          onSelectSeat={(seat, room) => {
                            if (!seat.agent) return;
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

        {selection ? (
          <aside className="seat-drawer">
            <div className="drawer-head">
              <span className={`drawer-avatar status-${selection.seat.agent?.status}`}>
                {selection.seat.agent?.display_name.slice(0, 1)}
              </span>
              <div>
                <strong>{selection.seat.agent?.display_name}</strong>
                <p>{selection.seat.agent?.position} · {selection.seat.agent?.team}</p>
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
        <span className="mono">
          实时信号 /api/stream · 布局 /api/public/layout{loadFailed ? " · 上次数据可能过期" : ""}
        </span>
      </footer>
    </div>
  );
}
