import { describe, expect, it, vi } from "vitest";
import { createSseFeed, parseStreamPayload } from "../twin/stream";

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
