import { api } from "../api";
import type { components } from "../contracts";

/**
 * Message 域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type MessageOut = components["schemas"]["mailbus__api__schemas__contract__message__MessageOut"];
type MessageIn = components["schemas"]["mailbus__api__schemas__contract__message__MessageIn"];
type MessageListOut = components["schemas"]["MessageListOut"];
type MessageTraceOut = components["schemas"]["MessageTraceOut"];

export function listMessages(query?: {
  employee_id?: string | null;
  channel?: "file_bus" | "a2a" | "mcp" | null;
  kind?: string | null;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (query?.employee_id) params.set("employee_id", query.employee_id);
  if (query?.channel) params.set("channel", query.channel);
  if (query?.kind) params.set("kind", query.kind);
  if (query?.limit !== undefined) params.set("limit", String(query.limit));
  if (query?.offset !== undefined) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<MessageListOut>(q ? `/api/messages?${q}` : "/api/messages");
}

export function getMessage(messageId: string) {
  return api<MessageOut>(`/api/messages/${encodeURIComponent(messageId)}`);
}

export function sendMessage(body: MessageIn) {
  return api<MessageOut>("/api/messages", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function traceMessage(messageId: string) {
  return api<MessageTraceOut>(`/api/messages/${encodeURIComponent(messageId)}/trace`);
}

export function deleteMessage(messageId: string) {
  return api<MessageOut>(`/api/messages/${encodeURIComponent(messageId)}`, { method: "DELETE" });
}
