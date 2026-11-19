import { useEffect, useRef } from "react";
import type { Floor, Room, Seat, SeatAgent } from "./types";
import { planPath, pointBlocked, roomSpot } from "./pathfind";

const SHIRTS = ["#a8c8ee", "#cbb6e8", "#f6c9a0", "#a9d8c4", "#f2b6c6", "#f2d98f"];
const HAIRS = ["#f0d28c", "#f4afcb", "#a9785b", "#c9bbec", "#6e5344", "#c98b65"];
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

/** 稳定哈希：让每个员工的外观特征（眼镜 / 长发 / 背包）固定不变。 */
function hash(seed: string): number {
  let n = 0;
  for (let i = 0; i < seed.length; i += 1) n = (n * 31 + seed.charCodeAt(i)) % 9973;
  return n;
}

export interface Point {
  x: number;
  y: number;
}

export type WalkerAction =
  | "typing"     // 工位敲键盘
  | "resting"    // 沙发上瘫着
  | "standing"   // 站着聊天
  | "meeting"    // 开会（点头 + 手势）
  | "coffee"     // 端咖啡
  | "water"      // 举杯喝水
  | "fetch"      // 在饮水机前接水
  | "chat"       // 和同事聊天
  | "phone"      // 打电话
  | "stretch"    // 伸懒腰
  | "pair";      // 结对讨论（两人面对面）

/**
 * Walker 路线：走路 + 到达后的动作。
 * lifecycle: walk (RAF) → arrive → action (timeout) → done → onArrive
 */
export interface WalkerRoute {
  id: string;
  /** 出发工位；公开布局没有 agent_id 时作为员工稳定键。 */
  seatId: string;
  points: Point[];
  duration: number;
  agent: SeatAgent;
  /** 到达目的地后做什么动作（可选：省略则走完即消失）。 */
  action?: WalkerAction;
  /** 动作持续多久（ms），默认 4s。 */
  actionDuration?: number;
  /** 结对 id：同一 pairId 的两条路线会被连成一条协同线。 */
  pairId?: string;
  /** 到达后朝向的横坐标（结对时看向对方）。 */
  faceX?: number;
  /** 顶部任务徽标文案（任务协同链路）。 */
  taskLabel?: string;
}

interface WalkerProps {
  route: WalkerRoute;
  onArrive?: (routeId: string) => void;
  /** 本楼层所有门洞的位置（绝对坐标），用于触发开门动画。 */
  doors?: Array<{ roomId: string; x: number; y: number }>;
  /** walker 进入某扇门的触发半径时调用。 */
  onDoorEnter?: (roomId: string) => void;
  /** walker 离开某扇门的触发半径时调用。 */
  onDoorExit?: (roomId: string) => void;
}

/** 过门闸机：同一时刻只放行一个人，其余人在门口稍等。key = roomId，value = 占用到期时间。 */
const doorGate = new Map<string, number>();
const DOOR_GATE_MS = 700;

/** 走路 + 多动作状态机。 */
export function Walker({ route, onArrive, doors, onDoorEnter, onDoorExit }: WalkerProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const phaseRef = useRef<"walk" | "act" | "done">("walk");

  useEffect(() => {
    const node = nodeRef.current;
    if (!node) return;
    phaseRef.current = "walk";

    // 把 waypoint 序列展平成总距离
    let total = 0;
    const segLens: number[] = [];
    for (let i = 1; i < route.points.length; i += 1) {
      const d = Math.hypot(
        route.points[i].x - route.points[i - 1].x,
        route.points[i].y - route.points[i - 1].y,
      );
      segLens.push(d);
      total += d;
    }
    const speed = total / route.duration;

    let segIndex = 0;
    let segT = 0;
    let raf = 0;
    let last = performance.now();
    let facing = 1; // 1 = 朝右, -1 = 朝左（永远不倒立）

    // 过门检测：walker 当前所在的门洞集合，进入/离开时触发回调
    const DOOR_RADIUS = 60; // 触发半径（px），略大于门洞半宽，确保靠近即开且停留足够帧数
    const insideDoors = new Set<string>();

    const applyActionClass = () => {
      // 移除所有 state class，加 action 对应 class
      node.classList.remove(
        "is-walking", "is-typing", "is-resting", "is-standing",
        "is-meeting", "is-coffee", "is-water", "is-fetch", "is-chat", "is-phone", "is-stretch",
        "is-pair",
      );
      const cls = route.action ? `is-${route.action}` : "is-standing";
      node.classList.add(cls);
    };

    const frame = (now: number) => {
      if (phaseRef.current === "done") return;

      if (phaseRef.current === "walk") {
        const dt = now - last;
        last = now;
        segT += speed * dt;

        while (segIndex < segLens.length - 1 && segT >= segLens[segIndex]) {
          segT -= segLens[segIndex];
          segIndex += 1;
        }

        if (segIndex >= segLens.length - 1) {
          // 走完了 → 进入 action 阶段
          const end = route.points[route.points.length - 1];
          // 结对时转身看向对方
          if (route.faceX !== undefined && Math.abs(route.faceX - end.x) > 4) {
            facing = route.faceX > end.x ? 1 : -1;
          }
          node.style.transform = `translate(${end.x}px, ${end.y}px) scaleX(${facing}) translateZ(7px)`;
          node.style.setProperty("--facing", String(facing));
          applyActionClass();
          phaseRef.current = "act";

          // 到站后离开所有正在触发的门（让门关上）
          for (const id of insideDoors) onDoorExit?.(id);
          insideDoors.clear();

          const dur = route.actionDuration ?? 4000;
          if (!route.action || dur <= 0) {
            // 没动作 → 直接 done
            phaseRef.current = "done";
            onArrive?.(route.id);
            return;
          }
          // 设一个 timer，到点 call onArrive
          window.setTimeout(() => {
            if (phaseRef.current !== "done") {
              phaseRef.current = "done";
              onArrive?.(route.id);
            }
          }, dur);
          return; // 停掉 RAF
        }

        const a = route.points[segIndex];
        const b = route.points[segIndex + 1];
        const t = segLens[segIndex] > 0 ? segT / segLens[segIndex] : 1;
        const x = a.x + (b.x - a.x) * t;
        const y = a.y + (b.y - a.y) * t;
        // 只做水平翻转，绝不旋转整个人物（防止倒立）
        const dx = b.x - a.x;
        if (dx > 0.5) facing = 1;
        else if (dx < -0.5) facing = -1;

        // 过门检测：进入/离开门洞半径时触发开/关门回调。
        // 同一扇门同一时刻只放行一个人，其余人在门口等，避免几个人叠在一起穿门。
        let waiting = false;
        if (doors && doors.length) {
          const now = performance.now();
          const nowInside = new Set<string>();
          for (const d of doors) {
            const dist = Math.hypot(x - d.x, y - d.y);
            if (dist <= DOOR_RADIUS) nowInside.add(d.roomId);
          }
          for (const id of nowInside) {
            if (insideDoors.has(id)) {
              doorGate.set(id, now + DOOR_GATE_MS); // 占着门时不断续期
              continue;
            }
            if ((doorGate.get(id) ?? 0) > now) {
              waiting = true; // 门被占用，先等
              continue;
            }
            doorGate.set(id, now + DOOR_GATE_MS);
            insideDoors.add(id);
            onDoorEnter?.(id);
          }
          for (const id of insideDoors) {
            if (!nowInside.has(id)) {
              insideDoors.delete(id);
              if ((doorGate.get(id) ?? 0) <= now) doorGate.delete(id);
              onDoorExit?.(id);
            }
          }
        }
        if (waiting) {
          // 门口稍等，不推进进度
          raf = requestAnimationFrame(frame);
          return;
        }

        node.style.transform = `translate(${x}px, ${y}px) scaleX(${facing}) translateZ(7px)`;
        node.style.setProperty("--facing", String(facing));
        raf = requestAnimationFrame(frame);
      }
      // act 阶段不做 RAF，CSS animation 自己跑
    };

    raf = requestAnimationFrame(frame);
    return () => {
      phaseRef.current = "done";
      cancelAnimationFrame(raf);
      // 卸载时也关闭所有正在触发的门
      for (const id of insideDoors) onDoorExit?.(id);
      insideDoors.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.id]);

  const agent = route.agent;
  const tag = pick(TAGS, agent.display_name);
  const seed = agent.agent_id ?? agent.display_name;
  const h = hash(seed);
  const hasGlasses = h % 100 < 42;
  const hasLongHair = h % 7 === 0 || h % 7 === 3;
  const hasBackpack = h % 100 >= 68;
  // 手里的东西随动作变化：开会拿文件夹、敲键盘抱笔记本、喝水/接水端杯子
  const item =
    route.action === "coffee" ? "coffee" :
    route.action === "water" ? "water" :
    route.action === "fetch" ? "water" :
    route.action === "meeting" ? "folder" :
    route.action === "typing" ? "laptop" :
    "";
  return (
    <div
      ref={nodeRef}
      className={`walker is-walking${route.action ? "" : " walk-home"}`}
      data-seat={route.seatId}
      data-pair={route.pairId ?? undefined}
      style={{ "--tag": tag.tag, "--tag-text": tag.text } as React.CSSProperties}
    >
      <span
        className="walker-figure"
        style={
          {
            "--shirt": pick(SHIRTS, agent.display_name),
            "--hair": pick(HAIRS, agent.agent_id ?? agent.display_name),
          } as React.CSSProperties
        }
      >
        <i className="w-leg l1" />
        <i className="w-leg l2" />
        <i className="w-foot f1" />
        <i className="w-foot f2" />
        {hasBackpack ? <i className="w-backpack" /> : null}
        <i className="w-arm a1" />
        <i className="w-arm a2" />
        <i className="w-body" />
        <i className="w-collar" />
        <i className="w-lanyard" />
        <i className="w-badge" />
        <i className="w-head" />
        {hasLongHair ? <i className="w-hair w-hair-long" /> : <i className="w-hair" />}
        <i className="w-brow b1" />
        <i className="w-brow b2" />
        <i className="w-eye e1" />
        <i className="w-eye e2" />
        {hasGlasses ? <i className="w-glasses" /> : null}
        <i className="w-mouth" />
        <i className="w-blush b1" />
        <i className="w-blush b2" />
        {item ? <i className={`w-item w-item-${item}`} /> : null}
        {route.action === "fetch" ? <i className="w-stream" /> : null}
      </span>
      <span className="walker-tag">{agent.display_name}</span>
      {route.taskLabel ? <span className="walker-task">{route.taskLabel}</span> : null}
      {route.action === "pair" ? (
        <span className="w-speech">
          <i />
          <i />
          <i />
        </span>
      ) : null}
    </div>
  );
}

/** 根据目标房间 kind 决定做什么动作。 */
function actionFor(target: Room): { action: WalkerAction; actionDuration: number } {
  const pick = (list: WalkerAction[]) => list[Math.floor(Math.random() * list.length)];
  switch (target.kind) {
    case "lounge":
      return {
        action: pick(["fetch", "fetch", "water", "water", "coffee", "resting"]),
        actionDuration: 5000 + Math.random() * 3000,
      };
    case "meeting":
      return { action: pick(["meeting", "meeting", "standing"]), actionDuration: 4500 + Math.random() * 3000 };
    case "bullpen":
    case "focus":
      return { action: pick(["chat", "chat", "phone", "stretch", "typing"]), actionDuration: 3000 + Math.random() * 2500 };
    default:
      return { action: pick(["standing", "chat", "phone", "coffee"]), actionDuration: 3000 + Math.random() * 1800 };
  }
}

/** 工位前的可站立点（椅子前方 / 侧后方）。 */
function standSpots(room: Room, seat: Seat): Point[] {
  const sx = room.x + seat.x;
  const sy = room.y + seat.y;
  return [
    { x: sx, y: sy + 50 },
    { x: sx, y: sy + 56 },
    { x: sx + 12, y: sy + 50 },
    { x: sx - 12, y: sy + 50 },
    { x: sx, y: sy - 12 },
    { x: sx, y: sy },
  ];
}

/**
 * 规划一条完整的「走路 → 动作」路线：绕开墙体和桌子，只从门洞进出。
 * opts.from 传入时表示回程：从该点走回自己的工位，到达后不执行动作（随后落座）。
 */
export function planRoute(
  agent: SeatAgent,
  seat: Seat,
  floor: Floor,
  opts: {
    from?: Point;
    to?: Point;
    action?: WalkerAction;
    actionDuration?: number;
    pairId?: string;
    faceX?: number;
    taskLabel?: string;
  } = {},
): WalkerRoute | null {
  const homeRoom =
    floor.rooms.find((r) => r.seats.some((s) => s.seat_id === seat.seat_id)) ?? floor.rooms[0];

  let target: Room;
  if (opts.from) {
    target = homeRoom;
  } else {
    // 目标：55% 跨房间（去 lounge/meeting），45% 在自己房间内走动
    const others = floor.rooms.filter(
      (r) => r.room_id !== homeRoom.room_id && (r.kind === "lounge" || r.kind === "meeting"),
    );
    const crossRoom = others.length > 0 && Math.random() < 0.55;
    target = crossRoom ? others[Math.floor(Math.random() * others.length)] : homeRoom;
  }

  const act = opts.action
    ? { action: opts.action, actionDuration: opts.actionDuration ?? 6000 }
    : opts.from || opts.to
      ? null
      : actionFor(target);
  const starts = opts.from ? [opts.from] : standSpots(homeRoom, seat);
  // 接水/开会/喝咖啡/瘫着都要站到对应设施旁，其余动作在房间里找个空位。
  const cxRoom = target.x + target.w / 2;
  const cyRoom = target.y + target.h / 2;
  let dests: Point[];
  if (opts.to) {
    // 指定终点（例如电梯口）
    dests = [opts.to];
  } else if (opts.from) {
    dests = standSpots(homeRoom, seat);
  } else if (act?.action === "fetch") {
    // 茶水间的饮水机在 (w-64, 30)，站到它正下方接水。
    const cx = target.x + target.w - 64;
    const cy = target.y + 30;
    dests = [
      { x: cx + 15, y: cy + 46 },
      { x: cx + 6, y: cy + 50 },
      { x: cx + 26, y: cy + 44 },
      { x: cx - 10, y: cy + 46 },
      roomSpot(floor, target),
    ];
  } else if (act?.action === "meeting") {
    // 站到会议桌四角的椅子旁
    dests = [
      { x: cxRoom - 114, y: cyRoom - 24 },
      { x: cxRoom + 114, y: cyRoom - 24 },
      { x: cxRoom - 114, y: cyRoom + 38 },
      { x: cxRoom + 114, y: cyRoom + 38 },
      roomSpot(floor, target),
    ];
  } else if (act?.action === "coffee") {
    // 咖啡机在茶水间左下角 (24, h-60)，站到它右侧
    dests = [
      { x: target.x + 78, y: target.y + target.h - 42 },
      { x: target.x + 78, y: target.y + target.h - 52 },
      roomSpot(floor, target),
    ];
  } else if (act?.action === "resting") {
    // 沙发在房间正中偏上，站到沙发左侧
    dests = [
      { x: cxRoom - 118, y: cyRoom + 6 },
      { x: cxRoom + 118, y: cyRoom + 6 },
      roomSpot(floor, target),
    ];
  } else {
    dests = [roomSpot(floor, target)];
  }

  let path: Point[] | null = null;
  for (const s of starts) {
    if (pointBlocked(floor, s.x, s.y)) continue;
    for (const d of dests) {
      if (pointBlocked(floor, d.x, d.y)) continue;
      const p = planPath(floor, s, d);
      if (p && p.length > 1) {
        path = p;
        break;
      }
    }
    if (path) break;
  }
  // 走不过去就不派活，绝不穿墙、也不在原地假装走动
  if (!path) return null;

  const total = path.reduce(
    (sum, p, i) => (i === 0 ? 0 : sum + Math.hypot(p.x - path![i - 1].x, p.y - path![i - 1].y)),
    0,
  );
  // 绕行会更远，按 150px/s 折算时长
  const duration = Math.min(20000, Math.max(1200, (total / 150) * 1000));

  return {
    id: `${agent.agent_id ?? seat.seat_id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seatId: seat.seat_id,
    points: path,
    duration,
    agent,
    action: act?.action,
    actionDuration: act?.actionDuration,
    pairId: opts.pairId,
    faceX: opts.faceX,
    taskLabel: opts.taskLabel,
  };
}
