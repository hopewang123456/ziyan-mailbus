import type { components } from "../contracts";

/**
 * 协同域视图模型：只做展示映射，不新增服务端字段。
 * 组件只消费 view.ts 导出的类型，不直接依赖 contracts。
 */

type ScreenOut = components["schemas"]["ScreenOut"];
type PairOut = components["schemas"]["PairOut"];
type MessageOut = components["schemas"]["mailbus__api__schemas__message__MessageOut"];
type PublicScreenConfigOut = components["schemas"]["PublicScreenConfigOut"];

export type ScreenRow = {
  id: string;
  name: string;
  source: string;
  play_state: string;
  online: boolean;
  /** 草稿配置版本（当前 config_version） */
  config_version: number;
  /** 已发布配置版本（published_config_version），null 表示从未发布 */
  published_config_version: number | null;
  /** 是否有未发布草稿 */
  has_draft: boolean;
  /** 是否已发布过 */
  is_published: boolean;
  /** 上次心跳时间（服务端 last_seen_at） */
  last_seen_at: string | null;
  /** 活跃时间判定：120 秒内有心跳视为在线 */
  online_reason: string;
  team_bound: boolean;
};

export type PairRow = {
  id: string;
  initiator_id: string;
  partner_id: string;
  state: string;
  active: boolean;
  created_at: string;
  ended_at: string | null;
};

export type CollabMessageRow = {
  id: string;
  kind: string;
  body: string;
  sender_id: string;
  recipient_id: string | null;
  pair_id: string | null;
  delivery_status: string | null;
  created_at: string | null;
};

export type PublicScreenConfigRow = {
  screen_id: string;
  config_version: number;
  published: boolean;
  layout_type: string;
  theme: string;
  resolution: string;
  play_state: string;
  team_bound: boolean;
  /** 公开投影，不含 team_id / secret / endpoint / creator 等敏感字段 */
  office: Record<string, unknown> | null;
  grid: Record<string, unknown> | null;
  custom: Record<string, unknown> | null;
};

/** 判断 ISO UTC 时间是否在 N 秒内活跃过。 */
export function isRecentlyActive(iso: string | null | undefined, windowSeconds = 120): boolean {
  if (!iso) return false;
  try {
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return false;
    return Date.now() - t < windowSeconds * 1000;
  } catch {
    return false;
  }
}

export function mapScreen(s: ScreenOut): ScreenRow {
  const online = s.online ?? isRecentlyActive(s.last_seen_at, 120);
  const publishedVersion = s.published_config_version ?? null;
  const hasDraft =
    publishedVersion !== null ? s.config_version !== publishedVersion : true;
  return {
    id: s.screen_id,
    name: s.name,
    source: s.source,
    play_state: s.play_state,
    online,
    config_version: s.config_version,
    published_config_version: publishedVersion,
    has_draft: hasDraft,
    is_published: publishedVersion !== null,
    last_seen_at: s.last_seen_at ?? null,
    online_reason: online ? "活跃" : (s.last_seen_at ? "离线" : "未登记"),
    team_bound: s.team_bound,
  };
}

export function mapPair(p: PairOut): PairRow {
  return {
    id: p.pair_id,
    initiator_id: p.initiator_id,
    partner_id: p.partner_id,
    state: p.state,
    active: p.state === "active",
    created_at: p.created_at,
    ended_at: p.ended_at ?? null,
  };
}

export function mapMessage(m: MessageOut): CollabMessageRow {
  return {
    id: m.message_id,
    kind: m.kind,
    body: m.body,
    sender_id: m.sender_id,
    recipient_id: m.recipient_id ?? null,
    pair_id: m.pair_id ?? null,
    delivery_status: m.delivery_status ?? null,
    created_at: m.created_at ?? null,
  };
}

export function mapPublicScreenConfig(c: PublicScreenConfigOut): PublicScreenConfigRow {
  return {
    screen_id: c.screen_id,
    config_version: c.config_version,
    published: c.published,
    layout_type: c.layout_type,
    theme: c.theme,
    resolution: c.resolution,
    play_state: c.play_state,
    team_bound: c.team_bound,
    office: c.office ?? null,
    grid: c.grid ?? null,
    custom: c.custom ?? null,
  };
}

// === 标签 / 枚举 ===

export const PAIR_STATE_LABEL: Record<string, string> = {
  active: "进行中",
  ended: "已结束",
  pending: "待确认",
};

export const MESSAGE_KIND_LABEL: Record<string, string> = {
  note: "备注",
  command: "指令",
  reply: "回复",
  alert: "告警",
};

export const DELIVERY_STATUS_LABEL: Record<string, string> = {
  pending: "待投递",
  delivered: "已投递",
  failed: "投递失败",
  queued: "队列中",
};

export const PLAY_STATE_LABEL: Record<string, string> = {
  playing: "播放中",
  paused: "已暂停",
};

export const THEME_LABEL: Record<string, string> = {
  auto: "跟随系统",
  dark: "深色",
  light: "浅色",
};

export const LAYOUT_TYPE_LABEL: Record<string, string> = {
  office: "办公室",
  grid: "网格",
  custom: "自定义",
};

/** ISO 时间本地化。null / 非法 / 未来都安全降级。 */
export function timeText(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
