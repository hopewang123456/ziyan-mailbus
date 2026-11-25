import type { components } from "../contracts";

/**
 * Message 域视图模型。
 * contracts.ts 直接可用的 DTO 直接 re-export，复杂嵌套做浅层展平。
 */

export type MessageOut = components["schemas"]["mailbus__api__schemas__contract__message__MessageOut"];
export type MessageIn = components["schemas"]["mailbus__api__schemas__contract__message__MessageIn"];
export type MessageTraceOut = components["schemas"]["MessageTraceOut"];
export type MessageTraceEventOut = components["schemas"]["MessageTraceEventOut"];

export type MessageRow = MessageOut;

export type MessageDetailRow = MessageOut & {
  trace?: MessageTraceEventOut[];
};

export type TraceRow = MessageTraceEventOut;
