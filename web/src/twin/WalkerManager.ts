import { useCallback, useEffect, useRef, useState } from "react";
import type { Floor, Seat, SeatAgent } from "./types";
import { planRoute, type Point, type WalkerRoute } from "./Walker";
import { elevatorSpot, pointBlocked, roomSpot } from "./pathfind";

interface UseWalkersOptions {
  /** 最多同时在路上走多少个。 */
  maxConcurrent?: number;
  /** 生成新路线的间隔（ms）。 */
  tickMs?: number;
  /** 每个楼层是否启用（focused 才启用，避免 overview 渲染 walker）。 */
  enabled?: boolean;
}

/**
 * 管理一组 Walker 的活动。
 * 返回 routes 列表（含正在走的）+ startAgent / clearAll 方法。
 */
export function useWalkers(
  floors: Floor[],
  { maxConcurrent = 8, tickMs = 1600, enabled = true }: UseWalkersOptions = {},
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

  /** 结对协同：两个人走到同一间会议室/休息区，面对面讨论。 */
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
        const targets = floor.rooms.filter(
          (r) => r.kind === "meeting" || r.kind === "lounge",
        );
        if (!targets.length) continue;

        for (let attempt = 0; attempt < 10; attempt += 1) {
          const a = free[Math.floor(Math.random() * free.length)];
          const b = free[Math.floor(Math.random() * free.length)];
          if (a.seat.seat_id === b.seat.seat_id) continue;
          const room = targets[Math.floor(Math.random() * targets.length)];
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
            const pairId = `pair-${Date.now()}-${pairSeqRef.current}`;
            pairSeqRef.current += 1;
            const routeA = planRoute(a.seat.agent!, a.seat, floor, {
              to: pa,
              action: "pair",
              actionDuration: 9500 + Math.random() * 3000,
              pairId,
              faceX: pb.x,
            });
            const routeB = planRoute(b.seat.agent!, b.seat, floor, {
              to: pb,
              action: "pair",
              actionDuration: 9500 + Math.random() * 3000,
              pairId,
              faceX: pa.x,
            });
            if (!routeA || !routeB) continue;
            busyRef.current.set(a.seat.seat_id, 1);
            busyRef.current.set(b.seat.seat_id, 1);
            setRoutes((prev) => [...prev, routeA, routeB]);
            return true;
          }
        }
      }
      return false;
    },
    [floors],
  );

  /** 任务协同：把任务负责人派到会议室推进（带任务徽标）。 */
  const startTask = useCallback(
    (seatId: string, label: string): boolean => {
      if (busyRef.current.has(seatId)) return false;
      for (const floor of floors) {
        for (const room of floor.rooms) {
          const seat = room.seats.find((s) => s.seat_id === seatId);
          if (!seat?.agent) continue;
          const targets = floor.rooms.filter(
            (r) => r.kind === "meeting" || r.kind === "lounge",
          );
          const target = targets[0] ?? room;
          const route = planRoute(seat.agent, seat, floor, {
            to: roomSpot(floor, target),
            action: "meeting",
            actionDuration: 9000,
            taskLabel: label,
          });
          if (!route) continue;
          busyRef.current.set(seatId, 1);
          setRoutes((prev) => [...prev, route]);
          return true;
        }
      }
      return false;
    },
    [floors],
  );

  const tick = useCallback(() => {
    if (!enabled) return;
    if (routesRef.current.length >= maxConcurrent) return;

    // 偶发结对：两个人走到同一间会议室/休息区面对面讨论
    if (
      !routesRef.current.some((r) => r.pairId) &&
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
          if (seat.agent?.status === "online" && !busyRef.current.has(seat.seat_id)) {
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
      setRoutes((prev) => [...prev, route]);
      return;
    }
  }, [floors, maxConcurrent, enabled, startPair]);

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

  return { routes, removeRoute, clearAll, startPair, startTask };
}
