/**
 * @deprecated F6 后删除
 * 兼容薄包装：SSE 唯一实现已迁到 `lib/events.ts`。
 * 保留此文件仅为过渡期引用不中断；F6 删除。
 */
export {
  createSseFeed,
  createEventFeed,
  parseStreamPayload,
  useCollabEvents,
  useStreamSignal,
} from "../lib/events";

export type { StreamSnapshot, StreamState, SseEvent as CollabEvent } from "../lib/events";
