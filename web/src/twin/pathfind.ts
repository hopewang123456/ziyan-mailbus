import type { Floor, Room } from "./types";

export interface Pt {
  x: number;
  y: number;
}

const CELL = 6;
const W = 1400;
const H = 900;
// 视觉墙 = .room-floor 的 border:14px，content-box 下边框画在房间外侧
const WALL_OUT = 14;   // 墙在房间外侧 14px
const WALL_IN = 0;     // 墙不伸进房间内侧
const CHAR_R = 10;     // 人物半径（身体半宽约 11px，取 10 留 1px 余量）
const DOOR_W = 92;     // 门洞宽度（视觉 70px + 膨胀余量，确保人物舒适通过）

/**
 * 门朝向：优先选择朝向"走廊"（两排房间之间）的墙，避免门开在大楼外沿。
 * 判断：探测点不在任何房间内，且大楼边界内有其他房间在该方向上。
 */
export function chooseDoorWall(room: Room, rooms: Room[]): "n" | "s" | "w" | "e" {
  const probe = 40;
  // 大楼边界（含墙厚）
  const bMinX = Math.min(...rooms.map((r) => r.x - 14));
  const bMaxX = Math.max(...rooms.map((r) => r.x + r.w + 14));
  const bMinY = Math.min(...rooms.map((r) => r.y - 14));
  const bMaxY = Math.max(...rooms.map((r) => r.y + r.h + 14));

  const inRoom = (x: number, y: number) =>
    rooms.some((r) => x > r.x - 6 && x < r.x + r.w + 6 && y > r.y - 6 && y < r.y + r.h + 6);
  // 探测点必须在大楼边界内（不是大楼外沿）才算走廊
  const inCorridor = (x: number, y: number) =>
    !inRoom(x, y) && x > bMinX && x < bMaxX && y > bMinY && y < bMaxY;

  const prefs: Array<"n" | "s" | "w" | "e"> =
    room.kind === "meeting"
      ? ["n", "s", "e", "w"]
      : room.kind === "lounge" || room.kind === "reception"
        ? ["e", "s", "n", "w"]
        : ["n", "s", "e", "w"];

  for (const wall of prefs) {
    const p =
      wall === "n" ? { x: room.x + room.w / 2, y: room.y - probe }
      : wall === "s" ? { x: room.x + room.w / 2, y: room.y + room.h + probe }
      : wall === "w" ? { x: room.x - probe, y: room.y + room.h / 2 }
      : { x: room.x + room.w + probe, y: room.y + room.h / 2 };
    if (inCorridor(p.x, p.y)) return wall;
  }
  // 兜底：选第一个不在房间内的方向
  for (const wall of prefs) {
    const p =
      wall === "n" ? { x: room.x + room.w / 2, y: room.y - probe }
      : wall === "s" ? { x: room.x + room.w / 2, y: room.y + room.h + probe }
      : wall === "w" ? { x: room.x - probe, y: room.y + room.h / 2 }
      : { x: room.x + room.w + probe, y: room.y + room.h / 2 };
    if (!inRoom(p.x, p.y)) return wall;
  }
  return "s";
}

/** 门洞中心点的绝对坐标（楼层坐标系），用于门板定位与 walker 过门检测。 */
export function getDoorCenter(room: Room, wall: "n" | "s" | "w" | "e"): Pt {
  const cx = room.x + room.w / 2;
  const cy = room.y + room.h / 2;
  switch (wall) {
    case "n": return { x: cx, y: room.y };
    case "s": return { x: cx, y: room.y + room.h };
    case "w": return { x: room.x, y: cy };
    case "e": return { x: room.x + room.w, y: cy };
  }
}

/** 电梯位置：各层走廊里的固定落点（纯视觉，不参与寻路障碍）。 */
export function elevatorSpot(floor: Floor): Pt {
  const byLevel: Record<number, Pt> = {
    1: { x: 700, y: 340 },
    2: { x: 700, y: 640 },
    3: { x: 700, y: 640 },
  };
  return byLevel[floor.level] ?? { x: 700, y: 340 };
}

/** 房间门洞的半宽（寻路用 DOOR_W，视觉门板略窄）。 */
export const DOOR_HALF = DOOR_W / 2;

export interface Grid {
  cols: number;
  rows: number;
  blocked: Uint8Array;
}

const gridCache = new Map<string, Grid>();
const GRID_VERSION = "v5"; // 墙厚/门洞/家具/膨胀参数变更时递增，强制重建网格

/** 房间内不可穿越的家具（会议桌 / 沙发 / 前台台面），尺寸自适应房间大小。
 *  关键：膨胀后的家具不得覆盖房间四角，确保 roomSpot 能找到可站立点。 */
function roomFurniture(room: Room): Array<{ x0: number; y0: number; x1: number; y1: number }> {
  const cx = room.x + room.w / 2;
  const cy = room.y + room.h / 2;
  // roomSpot 的四角兜底点在 inset+6 处，inset = min(48, min(w,h)/5)
  const inset = Math.min(48, Math.floor(Math.min(room.w, room.h) / 5));
  const margin = inset + 6 + 4 + CHAR_R; // 家具边到房间边至少留这么多，保证四角空闲
  if (room.kind === "meeting") {
    const tw = Math.min(160, room.w - margin * 2);
    const th = Math.min(100, room.h - margin * 2);
    if (tw <= 0 || th <= 0) return [];
    return [{ x0: cx - tw / 2, y0: cy - th / 2, x1: cx + tw / 2, y1: cy + th / 2 }];
  }
  if (room.kind === "lounge") {
    const sw = Math.min(180, room.w - margin * 2);
    const sh = Math.min(100, room.h - margin * 2);
    if (sw <= 0 || sh <= 0) return [];
    return [{ x0: cx - sw / 2, y0: cy - sh / 2, x1: cx + sw / 2, y1: cy + sh / 2 }];
  }
  if (room.kind === "reception") {
    const rw = Math.min(200, room.w - margin * 2);
    const rh = Math.min(80, room.h - margin * 2);
    if (rw <= 0 || rh <= 0) return [];
    return [{ x0: cx - rw / 2, y0: cy - rh / 2, x1: cx + rw / 2, y1: cy + rh / 2 }];
  }
  return [];
}

function fillRect(
  g: Grid,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  value: 0 | 1,
) {
  const c0 = Math.max(0, Math.floor(x0 / CELL));
  const c1 = Math.min(g.cols - 1, Math.ceil(x1 / CELL));
  const r0 = Math.max(0, Math.floor(y0 / CELL));
  const r1 = Math.min(g.rows - 1, Math.ceil(y1 / CELL));
  for (let r = r0; r <= r1; r += 1) {
    for (let c = c0; c <= c1; c += 1) {
      const px = c * CELL + CELL / 2;
      const py = r * CELL + CELL / 2;
      if (px >= x0 && px <= x1 && py >= y0 && py <= y1) g.blocked[r * g.cols + c] = value;
    }
  }
}

function buildGrid(floor: Floor): Grid {
  const cols = Math.ceil(W / CELL);
  const rows = Math.ceil(H / CELL);
  const g: Grid = { cols, rows, blocked: new Uint8Array(cols * rows) };

  for (const room of floor.rooms) {
    const { x, y, w, h } = room;
    // 墙体外膨胀 CHAR_R：人物中心离墙至少一个半径，防止身体穿墙
    const wo = WALL_OUT + CHAR_R;
    const wi = WALL_IN + CHAR_R;

    // 四面墙（膨胀后）
    fillRect(g, x - wo, y - wo, x + w + wo, y + wi, 1); // 北墙
    fillRect(g, x - wo, y + h - wi, x + w + wo, y + h + wo, 1); // 南墙
    fillRect(g, x - wo, y - wo, x + wi, y + h + wo, 1); // 西墙
    fillRect(g, x + w - wi, y - wo, x + w + wo, y + h + wo, 1); // 东墙

    // 门洞：在选定的墙上挖开 DOOR_W 缺口（需覆盖膨胀后的墙体）
    const wall = chooseDoorWall(room, floor.rooms);
    const half = DOOR_W / 2;
    if (wall === "n") fillRect(g, x + w / 2 - half, y - wo, x + w / 2 + half, y + wi, 0);
    else if (wall === "s") fillRect(g, x + w / 2 - half, y + h - wi, x + w / 2 + half, y + h + wo, 0);
    else if (wall === "w") fillRect(g, x - wo, y + h / 2 - half, x + wi, y + h / 2 + half, 0);
    else fillRect(g, x + w - wi, y + h / 2 - half, x + w + wo, y + h / 2 + half, 0);

    // 工位桌面作为障碍（视觉桌面 92x52，椅子不挡路），膨胀 CHAR_R
    for (const seat of room.seats) {
      const sx = x + seat.x;
      const sy = y + seat.y;
      fillRect(g, sx - 46 - CHAR_R, sy - 26 - CHAR_R, sx + 46 + CHAR_R, sy + 26 + CHAR_R, 1);
    }

    // 房间中央家具，膨胀 CHAR_R
    for (const f of roomFurniture(room)) {
      fillRect(g, f.x0 - CHAR_R, f.y0 - CHAR_R, f.x1 + CHAR_R, f.y1 + CHAR_R, 1);
    }
  }

  return g;
}

function gridFor(floor: Floor): Grid {
  const key = `${floor.floor_id}-${GRID_VERSION}`;
  const cached = gridCache.get(key);
  if (cached) return cached;
  const g = buildGrid(floor);
  gridCache.set(key, g);
  return g;
}

/** 调试用：导出网格，供测试脚本检查墙/门位置 */
export function buildGridDebug(floor: Floor): Grid {
  return gridFor(floor);
}

/** 某个点能否站人（不在墙/桌子/家具里）。 */
export function pointBlocked(floor: Floor, x: number, y: number): boolean {
  const g = gridFor(floor);
  const c = Math.floor(x / CELL);
  const r = Math.floor(y / CELL);
  if (c < 0 || r < 0 || c >= g.cols || r >= g.rows) return true;
  return g.blocked[r * g.cols + c] === 1;
}

function isFree(g: Grid, x: number, y: number): boolean {
  const c = Math.floor(x / CELL);
  const r = Math.floor(y / CELL);
  if (c < 0 || r < 0 || c >= g.cols || r >= g.rows) return false;
  return g.blocked[r * g.cols + c] === 0;
}

export function lineFree(floor: Floor, a: Pt, b: Pt): boolean {
  const g = gridFor(floor);
  const dist = Math.hypot(b.x - a.x, b.y - a.y);
  const steps = Math.max(1, Math.ceil(dist / 2)); // 步长 2px，避免跳过薄墙
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    if (!isFree(g, a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)) return false;
  }
  return true;
}

/** 全场 A*：房间内部可走，但墙、桌子、家具不可穿越。 */
export function planPath(floor: Floor, start: Pt, end: Pt): Pt[] | null {
  const g = gridFor(floor);
  const toCell = (p: Pt) => ({
    c: Math.max(0, Math.min(g.cols - 1, Math.floor(p.x / CELL))),
    r: Math.max(0, Math.min(g.rows - 1, Math.floor(p.y / CELL))),
  });
  // 起点/终点必须本身就在空闲格上；若被阻挡直接返回 null，绝不跨墙找格子
  const neighbourFree = (c: number, r: number) => {
    if (c >= 0 && r >= 0 && c < g.cols && r < g.rows && g.blocked[r * g.cols + c] === 0) {
      return { c, r };
    }
    return null;
  };

  const s = neighbourFree(toCell(start).c, toCell(start).r);
  const e = neighbourFree(toCell(end).c, toCell(end).r);
  if (!s || !e) return null;

  const total = g.cols * g.rows;
  const idx = (c: number, r: number) => r * g.cols + c;
  const cost = new Float32Array(total).fill(Infinity);
  const prev = new Int32Array(total).fill(-1);
  const closed = new Uint8Array(total);
  const startIdx = idx(s.c, s.r);
  const goalIdx = idx(e.c, e.r);
  cost[startIdx] = 0;

  const heap: Array<{ i: number; f: number }> = [{ i: startIdx, f: 0 }];
  const push = (i: number, f: number) => {
    heap.push({ i, f });
    let k = heap.length - 1;
    while (k > 0) {
      const parent = (k - 1) >> 1;
      if (heap[parent].f <= heap[k].f) break;
      [heap[parent], heap[k]] = [heap[k], heap[parent]];
      k = parent;
    }
  };
  const pop = () => {
    const top = heap[0];
    const last = heap.pop()!;
    if (heap.length) {
      heap[0] = last;
      let k = 0;
      for (;;) {
        const l = k * 2 + 1;
        const rr = l + 1;
        let m = k;
        if (l < heap.length && heap[l].f < heap[m].f) m = l;
        if (rr < heap.length && heap[rr].f < heap[m].f) m = rr;
        if (m === k) break;
        [heap[m], heap[k]] = [heap[k], heap[m]];
        k = m;
      }
    }
    return top;
  };
  const octile = (c: number, r: number) => {
    const dc = Math.abs(c - e.c);
    const dr = Math.abs(r - e.r);
    return dc + dr + (Math.SQRT2 - 2) * Math.min(dc, dr);
  };

  let found = false;
  let guard = 0;
  while (heap.length && guard < total) {
    guard += 1;
    const { i } = pop();
    if (closed[i]) continue;
    closed[i] = 1;
    if (i === goalIdx) {
      found = true;
      break;
    }
    const c = i % g.cols;
    const r = (i - c) / g.cols;
    for (let dr = -1; dr <= 1; dr += 1) {
      for (let dc = -1; dc <= 1; dc += 1) {
        if (!dc && !dr) continue;
        const nc = c + dc;
        const nr = r + dr;
        if (nc < 0 || nr < 0 || nc >= g.cols || nr >= g.rows) continue;
        const ni = idx(nc, nr);
        if (g.blocked[ni] || closed[ni]) continue;
        if (dc && dr) {
          if (g.blocked[idx(c + dc, r)] || g.blocked[idx(c, r + dr)]) continue;
        }
        const step = dc && dr ? Math.SQRT2 : 1;
        const nc2 = cost[i] + step;
        if (nc2 < cost[ni]) {
          cost[ni] = nc2;
          prev[ni] = i;
          push(ni, nc2 + octile(nc, nr));
        }
      }
    }
  }
  if (!found) return null;

  const cells: Pt[] = [];
  let cur = goalIdx;
  while (cur !== -1) {
    const c = cur % g.cols;
    const r = (cur - c) / g.cols;
    cells.push({ x: c * CELL + CELL / 2, y: r * CELL + CELL / 2 });
    if (cur === startIdx) break;
    cur = prev[cur];
  }
  cells.reverse();
  cells[0] = { x: start.x, y: start.y };
  cells[cells.length - 1] = { x: end.x, y: end.y };

  // 贪心拉直：能从 i 直达 j 就跳过中间点
  const out: Pt[] = [cells[0]];
  let i = 0;
  while (i < cells.length - 1) {
    let j = cells.length - 1;
    for (; j > i + 1; j -= 1) {
      if (lineFree(floor, cells[i], cells[j])) break;
    }
    out.push(cells[j]);
    i = j;
  }
  return out;
}

/** 在房间内找一个可站立的目标点（避开桌椅家具）。 */
export function roomSpot(floor: Floor, room: Room): Pt {
  // 根据房间大小自适应内边距，确保不超出家具周围的通道
  const inset = Math.min(48, Math.floor(Math.min(room.w, room.h) / 5));
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const x = room.x + inset + Math.random() * Math.max(20, room.w - inset * 2);
    const y = room.y + inset + Math.random() * Math.max(20, room.h - inset * 2);
    if (!pointBlocked(floor, x, y)) return { x, y };
  }
  // 兜底：尝试房间四角附近（家具通常在中间）
  const corners = [
    { x: room.x + inset + 6, y: room.y + inset + 6 },
    { x: room.x + room.w - inset - 6, y: room.y + inset + 6 },
    { x: room.x + inset + 6, y: room.y + room.h - inset - 6 },
    { x: room.x + room.w - inset - 6, y: room.y + room.h - inset - 6 },
  ];
  for (const c of corners) {
    if (!pointBlocked(floor, c.x, c.y)) return c;
  }
  return { x: room.x + room.w / 2, y: room.y + room.h / 2 };
}
