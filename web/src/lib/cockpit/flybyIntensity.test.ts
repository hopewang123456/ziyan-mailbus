import { describe, expect, it } from "vitest";
import {
  _flybyState,
  flybyDt,
  intensityFromMetrics,
  setFlybyIntensity,
} from "./flybyIntensity";

const pts = (o: Record<string, number>) =>
  Object.entries(o).map(([metric, value]) => ({ metric, value }));

describe("intensityFromMetrics", () => {
  it("空闲（无指标）→ 0.55 安闲", () => {
    expect(intensityFromMetrics([])).toBeCloseTo(0.55);
  });

  it("单活跃任务小幅加速", () => {
    expect(intensityFromMetrics(pts({ "tasks.active": 3 }))).toBeCloseTo(0.55 + 3 / 8);
  });

  it("繁忙封顶 2.2", () => {
    const v = intensityFromMetrics(pts({ "tasks.active": 40, "bus.unread": 500 }));
    expect(v).toBeCloseTo(2.2);
  });

  it("未读/待办/告警按权重计入", () => {
    const v = intensityFromMetrics(
      pts({ "bus.unread": 100, "humanqueue.pending": 5, "alerts.active": 5 })
    );
    // 100*0.15 + 5*0.3 + 5*0.2 = 17.5 → 封顶
    expect(v).toBeCloseTo(2.2);
  });

  it("null 值不计入", () => {
    expect(
      intensityFromMetrics([{ metric: "tasks.active", value: null }])
    ).toBeCloseTo(0.55);
  });
});

describe("setFlybyIntensity / flybyDt", () => {
  it("写入后向目标平滑趋近", () => {
    setFlybyIntensity(2.2);
    let moved = 0;
    // 60fps × 2s 的帧积分：current 应显著接近 target 但未过冲
    for (let i = 0; i < 120; i++) moved += flybyDt(1 / 60);
    const { current, target } = _flybyState();
    expect(target).toBeCloseTo(2.2);
    expect(current).toBeGreaterThan(1);
    expect(current).toBeLessThanOrEqual(2.2);
    expect(moved).toBeGreaterThan(2); // 2s 帧积分 > 裸 dt 总位移（强度>1）
    expect(moved).toBeLessThan(2.2 * 2); // 未达目标直乘（渐进）
  });

  it("夹紧到 [0.4, 2.5]", () => {
    setFlybyIntensity(99);
    expect(_flybyState().target).toBe(2.5);
    setFlybyIntensity(-1);
    expect(_flybyState().target).toBe(0.4);
    setFlybyIntensity(Number.NaN);
    expect(_flybyState().target).toBe(1); // 非法值回落 1
  });
});

import { getMsgFlow, setMsgFlowFromTotal } from "./flybyIntensity";

describe("msgFlow（总线粒子=消息流速）", () => {
  it("相邻快照差分→流速增益", () => {
    setMsgFlowFromTotal(100, 0);
    setMsgFlowFromTotal(160, 60_000); // 1 分钟 60 条 → 封顶 1
    expect(getMsgFlow()).toBeCloseTo(1);
  });

  it("慢流量按比例", () => {
    setMsgFlowFromTotal(200, 0);
    setMsgFlowFromTotal(215, 60_000); // 15 条/分 → 0.25
    expect(getMsgFlow()).toBeCloseTo(0.25);
  });

  it("无新消息渐暗回落", () => {
    setMsgFlowFromTotal(0, 0);
    setMsgFlowFromTotal(60, 60_000);
    let v = 0;
    for (let i = 0; i < 300; i++) v = getMsgFlow(1 / 60); // ~5s
    expect(v).toBeLessThan(1);
    expect(v).toBeGreaterThan(0);
  });

  it("total 回退不计负", () => {
    setMsgFlowFromTotal(500, 0);
    setMsgFlowFromTotal(400, 60_000); // 重启清零场景
    expect(getMsgFlow()).toBeCloseTo(0);
  });
});
