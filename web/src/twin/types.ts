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
  /** 进行中的结对：公开布局直接下发 pair_id 与对方姓名。 */
  pair_id?: string;
  partner_name?: string;
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

/** 真实协同结对在大屏上的可视化锚点：两人工位的楼层绝对坐标。 */
export interface PairLink {
  pair_id: string;
  floor_id: string;
  /** 同一楼层才画连线、才能结伴走动；跨楼层仅在侧栏展示。 */
  same_floor: boolean;
  a_seat_id: string;
  b_seat_id: string;
  a_name: string;
  b_name: string;
  ax: number;
  ay: number;
  bx: number;
  by: number;
}

/** 公开协同消息（已脱敏，不含发送者/接收者身份）。 */
export interface PublicMessage {
  message_id: string;
  kind: string;
  body: string;
  created_at: string | null;
  delivery_status: string | null;
  pair_id: string | null;
}

/** 公开任务节点：只有名称、顺序与状态。 */
export interface PublicTaskNode {
  name: string;
  order: number;
  state: string;
}

/** 公开任务详情（已脱敏，无负责人/创建者/流程标识）。 */
export interface PublicTask {
  task_id: string;
  title: string;
  state: string;
  created_at: string | null;
  updated_at: string | null;
  nodes: PublicTaskNode[];
}

/** 大屏消息气泡：挂在某条结对连线的中点。 */
export interface PairBubble {
  pair_id: string;
  floor_id: string;
  message_id: string;
  body: string;
  created_at: string | null;
  x: number;
  y: number;
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
