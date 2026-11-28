import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { seatStats, type Floor, type PairBubble, type PairLink, type Room, type Seat } from "./types";
import { Walker, type WalkerRoute } from "./Walker";
import { chooseDoorWall, elevatorSpot, getDoorCenter } from "./pathfind";
import { personAppearance } from "./appearance";
import { PersonHoverCard } from "./PersonCard";

const WALL_H = 62;
export const FLOOR_GAP = 520;

const TAGS = [
  { tag: "#f5a9c8", text: "#e05893" },
  { tag: "#c3b0ee", text: "#8a6bcf" },
  { tag: "#a9c8f0", text: "#4f86c6" },
  { tag: "#a7dcc4", text: "#3e9e78" },
  { tag: "#f2d48f", text: "#c79b2e" },
];

function pick<T>(list: T[], seed: string): T {
  let n = 0;
  for (const ch of seed) n += ch.charCodeAt(0);
  return list[n % list.length];
}

/** 稳定哈希：用于给工位分配固定的小摆件（台灯、文件盒等）。 */
function seedNum(seed: string): number {
  let n = 0;
  for (let i = 0; i < seed.length; i += 1) n = (n * 31 + seed.charCodeAt(i)) % 9973;
  return n;
}

/** 根据 seatId 在楼层中反查工位与所属房间（用于 walker 点击选中，让走动中的员工也能查看详情）。 */
function locateSeat(floor: Floor, seatId: string): { seat: Seat; room: Room } | null {
  for (const room of floor.rooms) {
    const seat = room.seats.find((s) => s.seat_id === seatId);
    if (seat) return { seat, room };
  }
  return null;
}

/** 消息时间：当天显示 HH:mm，跨天显示 MM-DD HH:mm（无需定时刷新）。 */
function formatMessageTime(iso: string | null): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  const clock = `${pad(at.getHours())}:${pad(at.getMinutes())}`;
  return at.toDateString() === new Date().toDateString()
    ? clock
    : `${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${clock}`;
}

/**
 * 真实协同结对连线：在同一楼层两名结对员工工位之间画一条流动虚线，
 * 中点标注「A ⇄ B」，并在其上方显示该结对最新的公开消息气泡。
 * 跨楼层结对不画线，只在侧栏展示。
 */
function PairLinks({ links, bubbles }: { links?: PairLink[]; bubbles?: PairBubble[] }) {
  const list = (links ?? []).filter((link) => link.same_floor);
  if (list.length === 0) return null;
  return (
    <div className="pair-links" aria-hidden>
      {list.map((link) => (
        <svg key={link.pair_id} className="pair-link-svg" width="100%" height="100%">
          <line
            className="pair-link-line"
            x1={link.ax}
            y1={link.ay}
            x2={link.bx}
            y2={link.by}
          />
          <circle className="pair-link-node" cx={link.ax} cy={link.ay} r={10} />
          <circle className="pair-link-node" cx={link.bx} cy={link.by} r={10} />
        </svg>
      ))}
      {list.map((link) => (
        <span
          key={`${link.pair_id}-label`}
          className="pair-link-label"
          style={{
            left: (link.ax + link.bx) / 2,
            top: (link.ay + link.by) / 2,
          }}
        >
          {link.a_name} ⇄ {link.b_name}
        </span>
      ))}
      {(bubbles ?? []).map((bubble) => (
        <div
          key={bubble.message_id}
          className="pair-bubble"
          style={{ left: bubble.x, top: bubble.y - 34 }}
          title={bubble.body}
        >
          <span className="pair-bubble-body">{bubble.body}</span>
          <span className="pair-bubble-time">{formatMessageTime(bubble.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

interface SeatViewProps {
  seat: Seat;
  room: Room;
  selected: boolean;
  /** 该员工此刻正在走动，工位上不再渲染坐姿小人 */
  walking?: boolean;
  /** 任务刚发生变化，工位外圈脉冲提示 */
  pulsing?: boolean;
  onSelect: (seat: Seat, room: Room) => void;
}

/** 坐姿小人的随机待机动作。 */
type IdleAction = "type" | "drink" | "stretch" | "look" | "phone";

function pickIdle(): IdleAction {
  const r = Math.random();
  if (r < 0.46) return "type";
  if (r < 0.66) return "drink";
  if (r < 0.79) return "stretch";
  if (r < 0.91) return "look";
  return "phone";
}

/** 俯视人物：头发 + 头 + 肩膀，坐在椅子上；姓名牌竖在工位后方。 */
function SeatView({
  seat,
  room,
  selected,
  walking = false,
  pulsing = false,
  onSelect,
}: SeatViewProps) {
  const agent = seat.agent;
  const tag = agent ? pick(TAGS, agent.display_name) : null;
  const look = agent ? personAppearance(agent.agent_id ?? agent.display_name) : null;
  const [idle, setIdle] = useState<IdleAction>("type");

  // 在线员工每隔几秒换一个待机动作：敲键盘 / 喝水 / 伸懒腰 / 张望 / 打电话
  useEffect(() => {
    if (!agent || agent.status !== "online") return;
    let timer = 0;
    const loop = (delay: number) => {
      timer = window.setTimeout(() => {
        setIdle(pickIdle());
        loop(3800 + Math.random() * 4200);
      }, delay);
    };
    loop(1800 + Math.random() * 4200);
    return () => window.clearTimeout(timer);
  }, [agent?.agent_id, agent?.display_name, agent?.status]);

  // 忙碌的人固定在电脑前敲键盘；在线空闲的人轮换待机动作；离线无动画。
  const idleClass = agent
    ? agent.status === "online"
      ? ` idle-${idle}`
      : agent.status === "busy"
        ? " idle-type"
        : ""
    : "";
  const progressTotal = agent?.progress_total ?? 0;
  const progressPct =
    progressTotal > 0
      ? Math.min(100, Math.round(((agent?.progress_done ?? 0) / progressTotal) * 100))
      : 0;
  const sn = seedNum(seat.seat_id);
  const hasLamp = sn % 3 === 0;
  const hasBox = sn % 4 === 1;
  return (
    <div
      className={`seat${pulsing ? " is-pulsing" : ""}`}
      style={{ left: seat.x - room.x, top: seat.y - room.y }}
    >
      <div className="desk-top" />
      <div className="desk-monitor" />
      <div className="desk-monitor-stand" />
      <div className="desk-keyboard" />
      <div className="desk-mouse" />
      <div className="desk-mug" />
      <div className="desk-notes" />
      <div className="desk-pen" />
      {hasLamp ? <div className="desk-lamp" /> : null}
      {hasBox ? <div className="desk-box" /> : null}
      <div className="desk-chair" />
      {agent && !walking ? (
        <button
          type="button"
          className={`seat-person status-${agent.status}${idleClass}${selected ? " is-selected" : ""}`}
          style={{
            "--shirt": look!.shirt,
            "--shirt-accent": look!.shirtAccent,
            "--hair": look!.hair,
            "--skin": look!.skin,
            "--fig-w": String(look!.figW),
            "--head": String(look!.head),
            "--acc-color": look!.accessoryColor,
            "--tag": tag!.tag,
            "--tag-text": tag!.text,
          } as React.CSSProperties}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(seat, room);
          }}
          onPointerDown={(e) => e.stopPropagation()}
          aria-label={`${agent.display_name} · ${agent.position}`}
        >
          <i
            className="busy-ring"
            style={{ "--p": `${progressPct * 3.6}deg` } as React.CSSProperties}
            aria-hidden
          />
          <span className="person-figure">
            <i className="p-leg l1" />
            <i className="p-leg l2" />
            <i className="p-foot f1" />
            <i className="p-foot f2" />
            <i className="p-arm a1" />
            <i className="p-arm a2" />
            {look!.backpack ? <i className="p-backpack" /> : null}
            <i className="p-body" />
            <i className="p-collar" />
            <i className="p-lanyard" />
            <i className="p-badge" />
            <span className="person-head-group">
              <i className="p-head" />
              <i className={`p-hair${look!.hairStyle === "short" ? "" : ` p-hair-${look!.hairStyle}`}`} />
              {look!.accessory === "cap" ? <i className="acc acc-cap" /> : null}
              <i className="p-brow b1" />
              <i className="p-brow b2" />
              <i className="p-eye e1" />
              <i className="p-eye e2" />
              {look!.glasses ? <i className="p-glasses" /> : null}
              <i className="p-mouth" />
              {look!.accessory === "beard" ? <i className="acc acc-beard" /> : null}
              <i className="p-blush b1" />
              <i className="p-blush b2" />
              {look!.accessory === "headphones" ? <i className="acc acc-headphones" /> : null}
            </span>
            {look!.accessory === "tie" ? <i className="acc acc-tie" /> : null}
            <i className="p-dot" />
          </span>
          <span className="person-plate">{agent.display_name}</span>
          <PersonHoverCard agent={agent} />
        </button>
      ) : !agent ? (
        <div className="seat-empty" />
      ) : null}
    </div>
  );
}

/** 沿北墙依次排布挂件：让开左上角房间名牌与北墙门洞，放不下的直接跳过。 */
function northRow(
  roomW: number,
  doorWall: "n" | "s" | "w" | "e",
  widths: number[],
): Array<number | null> {
  const gap = 14;
  const doorL = roomW / 2 - 50;
  const doorR = roomW / 2 + 50;
  const out: Array<number | null> = [];
  let x = 150; // 左上角留给房间名牌
  for (const w of widths) {
    if (doorWall === "n" && x < doorR && x + w > doorL) x = doorR + gap;
    if (x + w > roomW - 24) {
      out.push(null);
      continue;
    }
    out.push(x);
    x += w + gap;
  }
  return out;
}

/** 饮水机：机身 + 水桶 + 龙头 + 纸杯架 + 接水盘。 */
function Cooler({ style }: { style: React.CSSProperties }) {
  return (
    <span className="prop prop-cooler" style={style}>
      <i className="cooler-cups" />
      <i className="cooler-drip" />
    </span>
  );
}

/** 办公设施：饮水机、打印机、白板、茶水台、文件柜、垃圾桶、绿植、挂钟等。 */
function Props({ room, doorWall }: { room: Room; doorWall: "n" | "s" | "w" | "e" }) {
  // 地面道具统一贴四角摆放：北墙挂件走顶部条带（避开桌子），
  // 落地道具放左右下角（避开最后一排椅子和门洞）。
  const floorProps = [
    <span key="ftree" className="prop prop-ftree" style={{ left: 16, top: room.h - 52 }} />,
    <span key="ext" className="prop prop-extinguisher" style={{ left: room.w - 26, top: room.h - 96 }} />,
  ];

  if (room.kind === "meeting") {
    const [wbX, shelfX, clockX, acX] = northRow(room.w, doorWall, [86, 78, 26, 44]);
    return (
      <>
        {wbX !== null ? <span className="prop prop-whiteboard" style={{ left: wbX, top: 0 }} /> : null}
        {shelfX !== null ? <span className="prop prop-shelf" style={{ left: shelfX, top: 0 }} /> : null}
        {clockX !== null ? <span className="prop prop-clock" style={{ left: clockX, top: 0 }} /> : null}
        {acX !== null ? <span className="prop prop-ac" style={{ left: acX, top: 2 }} /> : null}
        <Cooler style={{ left: room.w - 54, top: 22 }} />
        {floorProps}
        <span className="prop prop-trash" style={{ left: room.w - 30, top: room.h - 70 }} />
      </>
    );
  }

  if (room.kind === "lounge") {
    const [acX, shelfX, clockX] = northRow(room.w, doorWall, [44, 120, 26]);
    return (
      <>
        <span className="prop prop-counter" style={{ left: 24, top: 26 }} />
        <Cooler style={{ left: room.w - 64, top: 30 }} />
        <span className="prop prop-coffee" style={{ left: 24, top: room.h - 60 }} />
        <span className="prop prop-cups" style={{ left: 150, top: room.h - 48 }} />
        <span className="prop prop-fridge" style={{ left: room.w - 74, top: room.h - 88 }} />
        <span className="prop prop-microwave" style={{ left: 152, top: 30 }} />
        {shelfX !== null ? <span className="prop prop-shelf" style={{ left: shelfX, top: 0 }} /> : null}
        {clockX !== null ? <span className="prop prop-clock" style={{ left: clockX, top: 0 }} /> : null}
        {acX !== null ? <span className="prop prop-ac" style={{ left: acX, top: 2 }} /> : null}
        {floorProps}
        <span className="prop prop-trash" style={{ left: room.w - 30, top: room.h - 70 }} />
      </>
    );
  }

  if (room.kind === "reception") {
    const [logoX, acX] = northRow(room.w, doorWall, [90, 44]);
    return (
      <>
        {logoX !== null ? <span className="prop prop-logo" style={{ left: logoX, top: 0 }} /> : null}
        {acX !== null ? <span className="prop prop-ac" style={{ left: acX, top: 2 }} /> : null}
        <span className="prop prop-cabinet" style={{ left: 22, top: room.h - 52 }} />
        <span className="prop prop-printer" style={{ left: room.w - 52, top: room.h - 52 }} />
        <span className="prop prop-trash" style={{ left: room.w - 30, top: room.h - 70 }} />
        {floorProps.filter((prop) => prop.key !== "ftree")}
      </>
    );
  }

  const [acX, wbX, clockX, noticeX] = northRow(room.w, doorWall, [44, 86, 26, 52]);
  return (
    <>
      {wbX !== null ? <span className="prop prop-whiteboard" style={{ left: wbX, top: 0 }} /> : null}
      {clockX !== null ? <span className="prop prop-clock" style={{ left: clockX, top: 0 }} /> : null}
      {noticeX !== null ? <span className="prop prop-notice" style={{ left: noticeX, top: 4 }} /> : null}
      {acX !== null ? <span className="prop prop-ac" style={{ left: acX, top: 2 }} /> : null}
      <Cooler style={{ left: room.w - 54, top: 22 }} />
      <span className="prop prop-printer" style={{ left: room.w - 52, top: room.h - 52 }} />
      <span className="prop prop-trash" style={{ left: room.w - 30, top: room.h - 70 }} />
      {floorProps.filter((prop) => prop.key !== "ftree")}
    </>
  );
}

/** 房间家具与设施，让空房间不再空落落。 */
function RoomDecor({ room, doorWall }: { room: Room; doorWall: "n" | "s" | "w" | "e" }) {
  const cx = room.w / 2;
  const cy = room.h / 2;

  return (
    <>
      {/* 地毯先渲染，保证位于桌椅与人物之下；工区已有专属地毯不重复叠加 */}
      {room.kind === "meeting" || room.kind === "lounge" || room.kind === "reception" ? (
        <span
          className={`rug rug-${room.kind}`}
          style={{ width: room.w - 76, height: room.h - 76, left: 38, top: 38 }}
        />
      ) : null}

      {room.kind === "meeting" ? (
        <div className="decor" style={{ left: cx, top: cy }}>
          <span className="meeting-table" />
          <span className="table-papers" />
          <span className="table-bottles" />
          <span className="meeting-chair c1" />
          <span className="meeting-chair c2" />
          <span className="meeting-chair c3" />
          <span className="meeting-chair c4" />
          <span className="plant p1" />
          <span className="plant p2" />
        </div>
      ) : null}

      {room.kind === "lounge" ? (
        <div className="decor" style={{ left: cx, top: cy }}>
          <span className="sofa-main" />
          <span className="sofa-back" />
          <span className="sofa-arm left" />
          <span className="sofa-arm right" />
          <span className="sofa-cushion" />
          <span className="coffee-table" />
          <span className="table-mug" style={{ left: 18, top: 54 }} />
          <span className="desk-notes" style={{ left: -26, top: 56 }} />
          <span className="plant p1" />
          <span className="plant p2" />
          <span className="plant p3" style={{ left: 68, top: Math.min(104, cy - 46) }} />
        </div>
      ) : null}

      {room.kind === "reception" ? (
        <div className="decor" style={{ left: cx, top: cy }}>
          <span className="reception-counter" style={{ top: 34 }} />
          <span className="reception-glow" style={{ top: 0 }} />
          <span className="table-mug" style={{ left: 52, top: 48 }} />
          <span className="desk-notes" style={{ left: -54, top: 48 }} />
          <span className="plant p1" style={{ left: -cx + 18, top: 26 }} />
        </div>
      ) : null}

      {room.kind === "bullpen" || room.kind === "focus" ? (
        <div className="decor" style={{ left: 0, top: 0 }}>
          <span className="rug" style={{ width: room.w - 40, height: room.h - 40 }} />
          <span className="plant p1" style={{ left: 18, top: room.h - 46 }} />
        </div>
      ) : null}

      <div className="decor" style={{ left: 0, top: 0 }}>
        <Props room={room} doorWall={doorWall} />
      </div>
    </>
  );
}

function RoomView({
  room,
  doorWall,
  selectedSeatId,
  walkingSeatIds,
  doorOpen,
  pulseSeatId,
  onSelectSeat,
}: {
  room: Room;
  doorWall: "n" | "s" | "w" | "e";
  selectedSeatId: string | null;
  walkingSeatIds: Set<string>;
  doorOpen?: boolean;
  pulseSeatId?: string | null;
  onSelectSeat: (seat: Seat, room: Room) => void;
}) {
  const wall = doorWall;
  const door =
    wall === "n"
      ? { x: room.w / 2, y: 0 }
      : wall === "s"
        ? { x: room.w / 2, y: room.h }
        : wall === "w"
          ? { x: 0, y: room.h / 2 }
          : { x: room.w, y: room.h / 2 };
  const doorStyle: React.CSSProperties = (() => {
    const size = 84;
    switch (wall) {
      case "n": return { left: door.x - size / 2, top: -WALL_H, width: size, height: WALL_H };
      case "s": return { left: door.x - size / 2, top: `calc(100% - ${WALL_H}px)`, width: size, height: WALL_H };
      case "w": return { left: -WALL_H, top: door.y - size / 2, width: WALL_H, height: size };
      case "e": return { left: `calc(100% - ${WALL_H}px)`, top: door.y - size / 2, width: WALL_H, height: size };
    }
  })();

  return (
    <div
      className={`room room-${room.kind}${doorOpen ? " door-open" : ""}`}
      style={{ left: room.x, top: room.y, width: room.w, height: room.h }}
    >
      <div className="room-floor" />
      <span className="wall wall-n" style={{ top: -WALL_H, height: WALL_H }} />
      <span className="wall wall-s" style={{ top: `calc(100% - ${WALL_H}px)`, height: WALL_H }} />
      <span className="wall wall-w" style={{ left: -WALL_H, width: WALL_H, height: "100%" }} />
      <span className="wall wall-e" style={{ left: `calc(100% - ${WALL_H}px)`, width: WALL_H, height: "100%" }} />
      {/* 在主墙上开 doorway 缺口，用 room-floor 色填充，造成"穿墙"视觉 */}
      <span className={`doorway doorway-${wall}`} style={doorStyle} />
      <RoomDecor room={room} doorWall={wall} />
      <span className="room-label">{room.name}</span>
      {room.seats.map((seat) => (
        <SeatView
          key={seat.seat_id}
          seat={seat}
          room={room}
          walking={!!seat.agent && walkingSeatIds.has(seat.seat_id)}
          selected={selectedSeatId === seat.seat_id}
          pulsing={pulseSeatId === seat.seat_id}
          onSelect={onSelectSeat}
        />
      ))}
    </div>
  );
}

interface FloorSlabProps {
  floor: Floor;
  index: number;
  active: boolean;
  dimmed: boolean;
  selectedSeatId: string | null;
  walkerRoutes?: WalkerRoute[];
  pairLinks?: PairLink[];
  pairBubbles?: PairBubble[];
  pulseSeatId?: string | null;
  onWalkerArrive?: (routeId: string) => void;
  onSelectFloor: (floorId: string) => void;
  onSelectSeat: (seat: Seat, room: Room) => void;
}

/** 走廊里的电梯：井道 + 双开滑动门，有人到门口时打开。 */
function Elevator({ floor, open }: { floor: Floor; open: boolean }) {
  const spot = elevatorSpot(floor);
  return (
    <div
      className={`elevator${open ? " is-open" : ""}`}
      style={{ left: spot.x - 42, top: spot.y - 28 }}
    >
      <span className="elev-frame" />
      <span className="elev-door d1" />
      <span className="elev-door d2" />
      <span className="elev-sign">EV</span>
    </div>
  );
}

/** 门的开合状态：roomId → 引用计数，最后一个通过的人离开后再关门。 */
function useDoors(floor: Floor) {
  const [openCounts, setOpenCounts] = useState<Record<string, number>>({});
  const closeTimers = useRef<Record<string, number>>({});

  // 本层所有门洞中心坐标，供 walker 判断是否经过
  // 用 useMemo 稳定引用，避免每次 FloorSlab 重渲染都 new 数组传给 Walker
  const doors = useMemo(
    () =>
      floor.rooms.map((room) => {
        const wall = chooseDoorWall(room, floor.rooms);
        const c = getDoorCenter(room, wall);
        return { roomId: room.room_id, wall, x: c.x, y: c.y };
      }),
    [floor],
  );

  // 稳定引用的 enter/exit，避免传给 Walker 的 props 每次都是新函数
  const enter = useCallback((roomId: string) => {
    if (closeTimers.current[roomId]) {
      clearTimeout(closeTimers.current[roomId]);
      delete closeTimers.current[roomId];
    }
    setOpenCounts((prev) => ({ ...prev, [roomId]: (prev[roomId] ?? 0) + 1 }));
  }, []);
  const exit = useCallback((roomId: string) => {
    // 延时 450ms 关闭，让开门动画播完
    closeTimers.current[roomId] = window.setTimeout(() => {
      setOpenCounts((prev) => {
        const n = (prev[roomId] ?? 1) - 1;
        const next = { ...prev };
        if (n <= 0) delete next[roomId];
        else next[roomId] = n;
        return next;
      });
      delete closeTimers.current[roomId];
    }, 450);
  }, []);

  // 卸载时清掉未执行的定时器，避免对已卸载组件 setState
  useEffect(
    () => () => {
      Object.values(closeTimers.current).forEach((t) => clearTimeout(t));
      closeTimers.current = {};
    },
    [],
  );

  return { doors, openDoors: new Set(Object.keys(openCounts)), enter, exit };
}

function FloorSlabInner({
  floor,
  index,
  active,
  dimmed,
  selectedSeatId,
  walkerRoutes = [],
  pairLinks,
  pairBubbles,
  pulseSeatId,
  onWalkerArrive,
  onSelectFloor,
  onSelectSeat,
}: FloorSlabProps) {
  const stats = seatStats(floor);
  const walkingSeatIds = new Set(walkerRoutes.map((route) => route.seatId));
  const { doors, openDoors, enter, exit } = useDoors(floor);
  const elevSpot = elevatorSpot(floor);
  const elevOpen = walkerRoutes.some((route) => {
    const p = route.points[route.points.length - 1];
    return Math.hypot(p.x - elevSpot.x, p.y - elevSpot.y) < 48;
  });
  return (
    <div
      className={`floor-group${active ? " is-active" : ""}${dimmed ? " is-dimmed" : ""}`}
      style={{ transform: `translateZ(${index * FLOOR_GAP}px)` }}
    >
      <div className="floor-lift" style={{ animationDelay: `${index * -2.4}s` }}>
        <div
          className="floor-badge"
          style={{ left: -230, top: 26 }}
          onClick={(e) => {
            e.stopPropagation();
            onSelectFloor(floor.floor_id);
          }}
        >
          <span className="badge-level">{floor.level}F</span>
          <span className="badge-name">{floor.name}</span>
          <span className="badge-meta">
            在线 {stats.online} · 空位 {stats.empty}
          </span>
        </div>

        <div
          className="floor-slab"
          onClick={() => onSelectFloor(floor.floor_id)}
          title={`点击进入 ${floor.name}`}
        >
          <div className="slab-edge slab-edge-s" />
          <div className="slab-edge slab-edge-e" />
          {floor.rooms.map((room) => (
            <RoomView
              key={room.room_id}
              room={room}
              doorWall={chooseDoorWall(room, floor.rooms)}
              doorOpen={openDoors.has(room.room_id)}
              selectedSeatId={selectedSeatId}
              walkingSeatIds={walkingSeatIds}
              pulseSeatId={pulseSeatId}
              onSelectSeat={onSelectSeat}
            />
          ))}
          <Elevator floor={floor} open={elevOpen} />
          {/* 真实结对连线：画在房间之上、走动人物之下 */}
          <PairLinks links={pairLinks} bubbles={pairBubbles} />
          {/* Walker 层：放在 rooms 之后，保证在房间地板之上、墙之下 */}
          <div className="walkers-layer">
            {walkerRoutes.map((route) => (
              <Walker
                key={route.id}
                route={route}
                doors={doors}
                onDoorEnter={enter}
                onDoorExit={exit}
                onArrive={onWalkerArrive}
                onSelect={() => {
                  const hit = locateSeat(floor, route.seatId);
                  if (hit) onSelectSeat(hit.seat, hit.room);
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export const FloorSlab = memo(FloorSlabInner);

// ── Detail 全屏独立视图 ──────────────────────────────────

interface FloorDetailViewProps {
  floor: Floor;
  selection: { seat: Seat; room: Room } | null;
  walkerRoutes?: WalkerRoute[];
  pairLinks?: PairLink[];
  pairBubbles?: PairBubble[];
  pulseSeatId?: string | null;
  onWalkerArrive?: (routeId: string) => void;
  onSelectSeat: (seat: Seat, room: Room) => void;
}

/**
 * 全屏独立办公室画面：
 * - 单楼层、2D 俯视图、铺满 twin-body
 * - 隐藏 3D stage / sky / building / shell
 * - 楼层自动缩放适配窗口
 * - Walker 全启用，人物在房间间走动
 */
function FloorDetailViewInner({
  floor,
  selection,
  walkerRoutes = [],
  pairLinks,
  pairBubbles,
  pulseSeatId,
  onWalkerArrive,
  onSelectSeat,
}: FloorDetailViewProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  // 本层所有门洞 + 开合状态
  const { doors, openDoors, enter, exit } = useDoors(floor);
  const elevSpot = elevatorSpot(floor);
  const elevOpen = walkerRoutes.some((route) => {
    const p = route.points[route.points.length - 1];
    return Math.hypot(p.x - elevSpot.x, p.y - elevSpot.y) < 48;
  });

  // 楼层包围盒（含墙厚），用于自适应缩放与居中
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const room of floor.rooms) {
    minX = Math.min(minX, room.x - WALL_H);
    minY = Math.min(minY, room.y - WALL_H);
    maxX = Math.max(maxX, room.x + room.w + WALL_H);
    maxY = Math.max(maxY, room.y + room.h + WALL_H);
  }
  const floorW = maxX - minX;
  const floorH = maxY - minY;

  useEffect(() => {
    const padding = 56;
    const apply = () => {
      const wrap = wrapperRef.current;
      if (!wrap) return;
      const wrapW = wrap.clientWidth - padding * 2;
      const wrapH = wrap.clientHeight - padding * 2;
      const s = Math.min(wrapW / floorW, wrapH / floorH, 1);
      setScale(s);
    };

    apply();
    window.addEventListener("resize", apply);
    return () => window.removeEventListener("resize", apply);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floor.floor_id, floorW, floorH]);

  // 过滤出本层的 walker（公开布局用 seatId 匹配）
  const floorSeatIds = new Set(floor.rooms.flatMap((r) => r.seats.map((s) => s.seat_id)));
  const floorWalkers = walkerRoutes.filter((route) => floorSeatIds.has(route.seatId));
  const walkingSeatIds = new Set(floorWalkers.map((route) => route.seatId));

  return (
    <div className={`floor-detail${selection ? " has-drawer" : ""}`} ref={wrapperRef}>
      {/* scaler 用缩放后的实际尺寸参与居中布局 */}
      <div
        className="detail-scaler"
        style={{ width: floorW * scale, height: floorH * scale }}
      >
        <div
          className="detail-floor"
          style={{
            width: floorW,
            height: floorH,
            transform: `scale(${scale})`,
          }}
        >
          <div
            className="detail-rooms"
            style={{ transform: `translate(${-minX}px, ${-minY}px)` }}
          >
            {floor.rooms.map((room) => (
              <RoomView
                key={room.room_id}
                room={room}
                doorWall={chooseDoorWall(room, floor.rooms)}
                selectedSeatId={selection?.seat.seat_id ?? null}
                walkingSeatIds={walkingSeatIds}
                pulseSeatId={pulseSeatId}
                doorOpen={openDoors.has(room.room_id)}
                onSelectSeat={onSelectSeat}
              />
            ))}
            <Elevator floor={floor} open={elevOpen} />
            <PairLinks links={pairLinks} bubbles={pairBubbles} />
            <div className="walkers-layer">
              {floorWalkers.map((route) => (
                <Walker
                  key={route.id}
                  route={route}
                  onArrive={onWalkerArrive}
                  doors={doors}
                  onDoorEnter={enter}
                  onDoorExit={exit}
                  onSelect={() => {
                    const hit = locateSeat(floor, route.seatId);
                    if (hit) onSelectSeat(hit.seat, hit.room);
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="floor-detail-hint">ESC 返回整楼 · 点击员工查看详情</div>
    </div>
  );
}

export const FloorDetailView = memo(FloorDetailViewInner);
