import { describe, expect, it, vi } from "vitest";
import { createEventFeed, createSseFeed, parseStreamPayload } from "../twin/stream";

describe("SSE 分帧解析", () => {
  it("按空行切帧，忽略心跳注释", () => {
    const frames: string[] = [];
    const feed = createSseFeed((data) => frames.push(data));
    feed(": heartbeat\n\n");
    expect(frames).toEqual([]);
  });

  it("处理跨 chunk 的半个帧与多帧", () => {
    const frames: string[] = [];
    const feed = createSseFeed((data) => frames.push(data));
    feed('data: {"a":');
    feed('1}\n\ndata: {"b":2}\n\n');
    expect(frames).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("兼容 CRLF 与多行 data", () => {
    const frames: string[] = [];
    const feed = createSseFeed((data) => frames.push(data));
    feed('data: {"a":1}\r\n\r\ndata: line1\ndata: line2\r\n\r\n');
    expect(frames).toEqual(['{"a":1}', "line1\nline2"]);
  });

  it("丢弃坏 JSON 与缺少 overview 的负载", () => {
    const onData = vi.fn();
    const feed = createSseFeed(onData);
    feed("data: not-json\n\ndata: {\"log\":[]}\n\n");
    expect(onData).toHaveBeenCalledTimes(2);
    expect(parseStreamPayload("not-json")).toBeNull();
    expect(parseStreamPayload('{"log":[]}')).toBeNull();
  });

  it("保留 overview 并归一化 log", () => {
    const snapshot = parseStreamPayload('{"overview":{"tasks_total":1},"log":[{"k":1}]}');
    expect(snapshot).toEqual({ overview: { tasks_total: 1 }, log: [{ k: 1 }] });
    expect(parseStreamPayload('{"overview":{"tasks_total":1}}')).toEqual({
      overview: { tasks_total: 1 },
      log: [],
    });
  });
});

describe("协同 SSE 事件解析", () => {
  it("保留 event 名称并忽略 ping", () => {
    const events: Array<{ event: string; data: string }> = [];
    const feed = createEventFeed((event) => events.push(event));
    feed(": ping\n\nevent: pair.started\ndata: {\"pair_id\":\"p1\"}\n\n");
    expect(events).toEqual([{ event: "pair.started", data: '{"pair_id":"p1"}' }]);
  });

  it("处理跨 chunk、多事件与无 event 默认 message", () => {
    const events: Array<{ event: string; data: string }> = [];
    const feed = createEventFeed((event) => events.push(event));
    feed("event: screen.focus\ndata: {\"screen_id\":");
    feed('"s1"}\n\ndata: {"ok":true}\n\n');
    expect(events).toEqual([
      { event: "screen.focus", data: '{"screen_id":"s1"}' },
      { event: "message", data: '{"ok":true}' },
    ]);
  });

  it("只有 event 没有 data 时不触发回调", () => {
    const onEvent = vi.fn();
    const feed = createEventFeed(onEvent);
    feed("event: pair.ended\n\n");
    expect(onEvent).not.toHaveBeenCalled();
  });
});
