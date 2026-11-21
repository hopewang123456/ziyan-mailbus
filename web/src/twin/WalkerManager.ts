import { useCallback, useEffect, useRef, useState } from "react";
import type { Floor, Seat, SeatAgent } from "./types";
import { planRoute, type Point, type WalkerRoute } from "./Walker";
import { elevatorSpot, pointBlocked, roomSpot } from "./pathfind";

/** 真实协同结对：两个工位上的员工被派去同一间会议室/休息区面对面讨论。 */
export interface RealPairLink {
  pairId: string;
  aSeatId: string;
  bSeatId: string;
}

interface UseWalkersOptions {
  /** 最多同时在路上走多少个。 */
  maxConcurrent?: number;
  /** 生成新路线的间隔（ms）。 */
  tickMs?: number;
  /** 每个楼层是否启用（focused 才启用，避免 overview 渲染 walker）。 */
  enabled?: boolean;
  /** 真实协同结对：优先派这两人结伴走动；存在时不再生成随机结对。 */
  realPairs?: RealPairLink[];
}

/** 在楼层里按 seatId 找到工位。 */
function findSeat(floor: Floor, seatId: string): Seat | null {
  for (const room of floor.rooms) {
    const seat = room.seats.find((s) => s.seat_id === seatId);
    if (seat) return seat;
  }
  return null;
}

/** 每人离座后至少回座待这么久，保证员工大部分时间都在工位上。 */
const LEAVE_COOLDOWN_MS = 45_000;

/**
 * 管理一组 Walker 的活动。
 * 返回 routes 列表（含正在走的）+ startAgent / clearAll 方法。
 */
export function useWalkers(
  floors: Floor[],
  { maxConcurrent = 8, tickMs = 1600, enabled = true, realPairs = [] }: UseWalkersOptions = {},
) {
  const [routes, setRoutes] = useState<WalkerRoute[]>([]);
  const routesRef = useRef<WalkerRoute[]>([]);
  routesRef.current = routes;

  /** seat_id → 当前活动数，避免同一员工同时被派两条路（公开布局无 agent_id） */
  const busyRef = useRef<Map<string, number>>(new Map());

  /** 电梯往返的延时任务，卸载时清理，避免对已卸载组件 setState */
  const timersRef = useRef<Set<number>>(new Set());
  useEffect(
    () => () => {
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current.clear();
    },
    [],
  );

  const pairSeqRef = useRef(0);

  /** 真实结对列表用 ref 保存，避免结对变化导致 tick 定时器重建。 */
  const realPairsRef = useRef<RealPairLink[]>(realPairs);
  realPairsRef.current = realPairs;
  /** 每个真实结对上次结伴走动的时间，避免刚回座又立刻出发。 */
  const pairCooldownRef = useRef<Map<string, number>>(new Map());
  /** seat_id → 上次离座时间：空闲员工也要先在工位待够时间才会走动。 */
  const leaveAtRef = useRef<Map<string, number>>(new Map());

  /** 把两人一起派到同一间会议室/休息区，面对面讨论。 */
  const sendPair = useCallback(
    (floor: Floor, a: Seat, b: Seat, pairId: string): boolean => {
      if (!a.agent || !b.agent) return false;
      const targets = floor.rooms.filter(
        (r) => r.kind === "meeting" || r.kind === "lounge",
      );
      if (!targets.length) return false;
      // 优先会议室，其次休息区
      const ordered = [...targets].sort(
        (x, y) => (x.kind === "meeting" ? -1 : 1) - (y.kind === "meeting" ? -1 : 1),
      );
      for (const room of ordered) {
        const cx = room.x + room.w / 2;
        const cy = room.y + room.h / 2;
        const spots: Array<[Point, Point]> =
          room.kind === "meeting"
            ? [
                [{ x: cx - 114, y: cy + 38 }, { x: cx + 114, y: cy + 38 }],
                [{ x: cx - 114, y: cy - 24 }, { x: cx + 114, y: cy - 24 }],
              ]
            : [
                [{ x: cx - 118, y: cy + 6 }, { x: cx + 118, y: cy + 6 }],
                [{ x: cx - 60, y: cy + 78 }, { x: cx + 60, y: cy + 78 }],
              ];
        for (const [pa, pb] of spots) {
          if (pointBlocked(floor, pa.x, pa.y) || pointBlocked(floor, pb.x, pb.y)) continue;
          const routeA = planRoute(a.agent, a, floor, {
            to: pa,
            action: "pair",
            actionDuration: 9500 + Math.random() * 3000,
            pairId,
            faceX: pb.x,
          });
          const routeB = planRoute(b.agent, b, floor, {
            to: pb,
            action: "pair",
            actionDuration: 9500 + Math.random() * 3000,
            pairId,
            faceX: pa.x,
          });
          if (!routeA || !routeB) continue;
          busyRef.current.set(a.seat_id, 1);
          busyRef.current.set(b.seat_id, 1);
          setRoutes((prev) => [...prev, routeA, routeB]);
          return true;
        }
      }
      return false;
    },
    [],
  );

  /** 随机结对：两人走到同一间会议室/休息区，面对面讨论（无真实结对时的氛围动画）。 */
  const startPair = useCallback(
    (onlyFloor?: Floor): boolean => {
      const pool = onlyFloor ? [onlyFloor] : floors;
      for (const floor of pool) {
        const free: Array<{ seat: Seat; room: Floor["rooms"][number] }> = [];
        for (const room of floor.rooms) {
          for (const seat of room.seats) {
            if (seat.agent?.status === "online" && !busyRef.current.has(seat.seat_id)) {
              free.push({ seat, room });
            }
          }
        }
        if (free.length < 2) continue;
        if (!floor.rooms.some((r) => r.kind === "meeting" || r.kind === "lounge")) continue;

        for (let attempt = 0; attempt < 10; attempt += 1) {
          const a = free[Math.floor(Math.random() * free.length)];
          const b = free[Math.floor(Math.random() * free.length)];
          if (a.seat.seat_id === b.seat.seat_id) continue;
          const pairId = `pair-${Date.now()}-${pairSeqRef.current}`;
          pairSeqRef.current += 1;
          if (sendPair(floor, a.seat, b.seat, pairId)) return true;
        }
      }
      return false;
    },
    [floors, sendPair],
  );

  const tick = useCallback(() => {
    if (!enabled) return;
    if (routesRef.current.length >= maxConcurrent) return;

    const hasPairRoute = routesRef.current.some((r) => r.pairId);
    const now = Date.now();
    const canLeave = (seatId: string) =>
      now - (leaveAtRef.current.get(seatId) ?? 0) >= LEAVE_COOLDOWN_MS;

    // 真实结对优先：把真实协同的两人一起派到会议室/休息区面对面讨论。
    if (
      !hasPairRoute &&
      routesRef.current.length <= maxConcurrent - 2 &&
      realPairsRef.current.length > 0
    ) {
      for (const link of realPairsRef.current) {
        if (now - (pairCooldownRef.current.get(link.pairId) ?? 0) < 45_000) continue;
        for (const floor of floors) {
          const a = findSeat(floor, link.aSeatId);
          const b = findSeat(floor, link.bSeatId);
          if (!a || !b || !a.agent || !b.agent) continue;
          // 只有两人都空闲（online）才结伴离座；忙碌的人默认坐定在工位。
          if (a.agent.status !== "online" || b.agent.status !== "online") continue;
          if (busyRef.current.has(a.seat_id) || busyRef.current.has(b.seat_id)) continue;
          if (!canLeave(a.seat_id) || !canLeave(b.seat_id)) continue;
          if (sendPair(floor, a, b, link.pairId)) {
            pairCooldownRef.current.set(link.pairId, now);
            leaveAtRef.current.set(a.seat_id, now);
            leaveAtRef.current.set(b.seat_id, now);
            return;
          }
        }
      }
    }

    // 偶发结对：有真实结对时不再生成随机结对，避免与真实数据冲突
    if (
      !hasPairRoute &&
      realPairsRef.current.length === 0 &&
      routesRef.current.length <= maxConcurrent - 2 &&
      Math.random() < 0.05 &&
      startPair()
    ) {
      return;
    }

    // 收集所有 online agent 及其 seat/floor 上下文
    const candidates: Array<{ agent: SeatAgent; floor: Floor; seat: Seat }> = [];
    for (const floor of floors) {
      for (const room of floor.rooms) {
        for (const seat of room.seats) {
          if (
            seat.agent?.status === "online" &&
            !busyRef.current.has(seat.seat_id) &&
            canLeave(seat.seat_id)
          ) {
            candidates.push({ agent: seat.agent, floor, seat });
          }
        }
      }
    }
    if (candidates.length === 0) return;

    // 随机挑一个；规划不出不穿墙的路线就跳过，绝不硬塞
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const pick = candidates[Math.floor(Math.random() * candidates.length)];

      // 偶发：坐电梯去别的楼层 —— 走到电梯口消失，稍后从电梯出来
      if (Math.random() < 0.14) {
        const elev = elevatorSpot(pick.floor);
        const out = planRoute(pick.agent, pick.seat, pick.floor, { to: elev });
        if (out) {
          busyRef.current.set(pick.seat.seat_id, (busyRef.current.get(pick.seat.seat_id) ?? 0) + 1);
          leaveAtRef.current.set(pick.seat.seat_id, now);
          setRoutes((prev) => [...prev, out]);
          const timer = window.setTimeout(() => {
            timersRef.current.delete(timer);
            const rooms = pick.floor.rooms.filter(
              (r) => r.kind === "lounge" || r.kind === "meeting",
            );
            const dest = rooms[Math.floor(Math.random() * rooms.length)] ?? pick.floor.rooms[0];
            const back = planRoute(pick.agent, pick.seat, pick.floor, {
              from: elev,
              to: roomSpot(pick.floor, dest),
            });
            if (!back) return;
            busyRef.current.set(
              pick.seat.seat_id,
              (busyRef.current.get(pick.seat.seat_id) ?? 0) + 1,
            );
            setRoutes((prev) => [...prev, back]);
          }, 2600);
          timersRef.current.add(timer);
          return;
        }
      }

      const route = planRoute(pick.agent, pick.seat, pick.floor);
      if (!route) continue;
      busyRef.current.set(pick.seat.seat_id, (busyRef.current.get(pick.seat.seat_id) ?? 0) + 1);
      leaveAtRef.current.set(pick.seat.seat_id, now);
      setRoutes((prev) => [...prev, route]);
      return;
    }
  }, [floors, maxConcurrent, enabled, startPair, sendPair]);

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(tick, tickMs);
    return () => window.clearInterval(id);
  }, [tick, tickMs, enabled]);

  const removeRoute = useCallback(
    (routeId: string) => {
      const found = routesRef.current.find((r) => r.id === routeId);

      // 做完动作后不原地消失，先走回自己的工位
      if (found && found.action) {
        const floor = floors.find((f) =>
          f.rooms.some((room) => room.seats.some((s) => s.seat_id === found.seatId)),
        );
        const seat = floor?.rooms
          .flatMap((room) => room.seats)
          .find((s) => s.seat_id === found.seatId);
        if (floor && seat) {
          const back = planRoute(found.agent, seat, floor, {
            from: found.points[found.points.length - 1],
          });
          if (back) {
            setRoutes((prev) => prev.map((r) => (r.id === routeId ? back : r)));
            return; // busy 计数保持不变，直到回家落座
          }
        }
      }

      setRoutes((prev) => {
        if (found) {
          const n = (busyRef.current.get(found.seatId) ?? 1) - 1;
          if (n <= 0) busyRef.current.delete(found.seatId);
          else busyRef.current.set(found.seatId, n);
        }
        return prev.filter((r) => r.id !== routeId);
      });
    },
    [floors],
  );

  const clearAll = useCallback(() => {
    setRoutes([]);
    busyRef.current.clear();
  }, []);

  return { routes, removeRoute, clearAll, startPair };
}
