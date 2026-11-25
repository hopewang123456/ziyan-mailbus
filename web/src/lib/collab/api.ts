import { api } from "../api";
import type { components } from "../contracts";

/**
 * 协同大屏域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 *
 * 后端契约要点（F6 核实）：
 *   - POST /api/collab/screens 不存在 → 新屏幕登记走 POST /api/public/collab/screens
 *   - GET /api/collab/screens/{id} 不存在 → 详情由 listScreens + 本地筛选兜底
 *   - PATCH /api/collab/screens/{id} 接收 ScreenDraftIn（保存草稿）
 *   - Pair / Messages 后端均直接返回数组，无分页 list_out 包装
 */

type ScreenListOut = components["schemas"]["ScreenListOut"];
type ScreenDraftIn = components["schemas"]["ScreenDraftIn"];
type ScreenConfigIn = components["schemas"]["ScreenConfigIn"];
type ScreenConfigOut = components["schemas"]["ScreenConfigOut"];
type ScreenRegisterIn = components["schemas"]["ScreenRegisterIn"];
type ScreenRegisterOut = components["schemas"]["ScreenRegisterOut"];
type ScreenPublishIn = components["schemas"]["ScreenPublishIn"];
type ScreenPublishOut = components["schemas"]["ScreenPublishOut"];
type ScreenFocusIn = components["schemas"]["ScreenFocusIn"];
type PairOut = components["schemas"]["PairOut"];
type PairIn = components["schemas"]["PairIn"];
type CollabMessageIn = components["schemas"]["CollabMessageIn"];
type MessageOut = components["schemas"]["mailbus__api__schemas__message__MessageOut"];
type PublicScreenConfigOut = components["schemas"]["PublicScreenConfigOut"];
type PublicTaskOut = components["schemas"]["PublicTaskOut"];
type SeatAssignIn = components["schemas"]["SeatAssignIn"];
type SeatOut = components["schemas"]["SeatOut"];
type PublicOfficeSiteOut = components["schemas"]["PublicOfficeSiteOut"];

// === 大屏管理（管理端 Bearer） ===

export interface ListScreensQuery {
  limit?: number;
  offset?: number;
}

export function listScreens(query: ListScreensQuery = {}) {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<ScreenListOut>(q ? `/api/collab/screens?${q}` : "/api/collab/screens");
}

/**
 * 后端没有 GET 详情；这里用列表筛选兜底。
 * 如果 F7 之后补了详情路由，改为直接 GET 即可，调用方无感知。
 */
export async function getScreen(id: string) {
  const result = await listScreens({ limit: 500 });
  if (!result.ok) return result as typeof result;
  const found = (result.data.items ?? []).find((s) => s.screen_id === id) ?? null;
  return { ok: true, data: found, status: result.status } as const;
}

export interface UpsertScreenBody {
  /** 更新草稿时必须带 screen_id；创建时留空由服务端分配（或本地先调 registerScreen）。 */
  id?: string;
  name?: string;
  /** 保存草稿时的配置；创建时可选。 */
  config?: ScreenConfigIn | null;
  play_state?: "playing" | "paused" | null;
  /** 创建时可选，绑定初始 seat。 */
  floor_id?: string | null;
  seat_id?: string | null;
}

/**
 * 创建：POST /api/public/collab/screens（公开登记，X-Screen-Secret 可选）
 * 更新：PATCH /api/collab/screens/{id}（保存草稿，ScreenDraftIn）
 *
 * 后端契约命名为 ScreenRegisterIn / ScreenDraftIn，前端统一叫 upsertScreen。
 */
export async function upsertScreen(body: UpsertScreenBody) {
  if (body.id) {
    // 不传 config 时后端保留现有草稿，只改 play_state。
    const draft: ScreenDraftIn = {
      config: body.config,
      play_state: body.play_state ?? null,
    };
    return api<ScreenConfigOut>(`/api/collab/screens/${encodeURIComponent(body.id)}`, {
      method: "PATCH",
      body: JSON.stringify(draft),
    });
  }
  // 创建
  const register: ScreenRegisterIn = {
    name: body.name ?? null,
    floor_id: body.floor_id ?? null,
    seat_id: body.seat_id ?? null,
    config: body.config,
  } as ScreenRegisterIn;
  return api<ScreenRegisterOut>("/api/public/collab/screens", {
    method: "POST",
    body: JSON.stringify(register),
  });
}

/**
 * 发布：把草稿 config_version 推进到 published_config_version。
 * 后端要求 expected_config_version（乐观锁）；这里传入调用方提供的值。
 */
export function publishScreen(id: string, expectedConfigVersion: number) {
  const body: ScreenPublishIn = { expected_config_version: expectedConfigVersion };
  return api<ScreenPublishOut>(
    `/api/collab/screens/${encodeURIComponent(id)}/publish`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function focusScreen(id: string, body: ScreenFocusIn) {
  return api(`/api/collab/screens/${encodeURIComponent(id)}/focus`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteScreen(id: string) {
  return api(`/api/collab/screens/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// === 结对 ===

export interface ListPairsQuery {
  state?: "active" | "ended" | null;
  limit?: number;
}

export function listPairs(query: ListPairsQuery = {}) {
  const params = new URLSearchParams();
  if (query.state) params.set("state", query.state);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  const q = params.toString();
  return api<PairOut[]>(q ? `/api/collab/pairs?${q}` : "/api/collab/pairs");
}

export function createPair(body: PairIn) {
  return api<PairOut>("/api/collab/pairs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function endPair(pair_id: string) {
  return api(`/api/collab/pairs/${encodeURIComponent(pair_id)}/end`, {
    method: "POST",
  });
}

// === 协同消息 ===

export interface ListMessagesQuery {
  pair_id?: string | null;
  /** 后端只支持 limit；offset 作为前端侧的过滤提示。 */
  limit?: number;
}

export function listMessages(query: ListMessagesQuery = {}) {
  const params = new URLSearchParams();
  if (query.pair_id) params.set("pair_id", query.pair_id);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  const q = params.toString();
  return api<MessageOut[]>(q ? `/api/collab/messages?${q}` : "/api/collab/messages");
}

export function sendMessage(body: CollabMessageIn) {
  return api<MessageOut>("/api/collab/messages", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// === 公开投影（孪生大屏，匿名也可） ===

export function publicScreenConfig(screen_id: string) {
  return api<PublicScreenConfigOut>(
    `/api/public/collab/screens/${encodeURIComponent(screen_id)}/config`,
  );
}

export function publicSeatTasks(seat_id: string) {
  return api<PublicTaskOut[]>(
    `/api/public/collab/seats/${encodeURIComponent(seat_id)}/tasks`,
  );
}

// === 布局编辑器辅助 ===

export function assignSeat(seat_id: string, body: SeatAssignIn) {
  return api<SeatOut>(`/api/seats/${encodeURIComponent(seat_id)}/assign`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function publicLayout() {
  return api<PublicOfficeSiteOut>("/api/public/layout");
}

export function listSeats(query?: { team_id?: string | null; limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.team_id) params.set("team_id", query.team_id);
  if (query?.limit !== undefined) params.set("limit", String(query.limit));
  if (query?.offset !== undefined) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<{ items: SeatOut[]; total: number; limit: number; offset: number }>(
    q ? `/api/seats?${q}` : "/api/seats",
  );
}
