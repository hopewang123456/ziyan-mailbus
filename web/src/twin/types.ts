/** 孪生办公室空间模型：site → floor → room → seat（与后端 layout.json 同构）。 */

export type AgentStatus = "online" | "busy" | "offline";

export type RoomKind = "reception" | "bullpen" | "focus" | "meeting" | "lounge";

export interface SeatAgent {
  /** 公开布局不返回 agent_id；前端用所在工位的 seat_id 兜底。 */
  agent_id?: string;
  /** Agent 台账名称 + 框架（公开布局脱敏后仍展示）。 */
  agent_name?: string;
  agent_framework?: string;
  display_name: string;
  position: string;
  team: string;
  status: AgentStatus;
  task: string;
  /** 任务执行态投影（当前节点 / 节点状态 / 进度）。 */
  task_id?: string;
  task_state?: string;
  current_node?: string;
  node_state?: string;
  progress_done?: number;
  progress_total?: number;
  /** 公开布局不返回心跳时间，缺失时显示「—」。 */
  last_heartbeat?: string;
}

export interface Seat {
  seat_id: string;
  /** 工位中心点，单位为楼层网格坐标（1400 × 900）。 */
  x: number;
  y: number;
  rotation: number;
  agent: SeatAgent | null;
}

export interface Room {
  room_id: string;
  name: string;
  kind: RoomKind;
  x: number;
  y: number;
  w: number;
  h: number;
  seats: Seat[];
}

export interface Floor {
  floor_id: string;
  name: string;
  level: number;
  rooms: Room[];
}

export interface OfficeSite {
  site_id: string;
  name: string;
  org_name: string;
  floors: Floor[];
}

export function floorSeats(floor: Floor): Seat[] {
  return floor.rooms.flatMap((room) => room.seats);
}

/** 员工在孪生里的稳定键：公开布局没有 agent_id，用 seat_id 兜底。 */
export function agentKey(seat: Seat): string {
  return seat.agent?.agent_id ?? seat.seat_id;
}

export function seatStats(floor: Floor) {
  const seats = floorSeats(floor);
  return {
    total: seats.length,
    occupied: seats.filter((s) => s.agent).length,
    online: seats.filter((s) => s.agent?.status === "online").length,
    busy: seats.filter((s) => s.agent?.status === "busy").length,
    offline: seats.filter((s) => s.agent?.status === "offline").length,
    empty: seats.filter((s) => !s.agent).length,
  };
}
