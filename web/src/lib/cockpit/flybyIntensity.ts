/**
 * D6 孤立映射→孪生映射（P4 第二批）：系统活跃度 → 飞掠强度。
 *
 * 数据源：/api/metrics/query?granularity=point（与驾驶舱指标卡同源同口径）。
 * 公式：intensity = 0.55 + min(1.65, 活跃单位/8)
 *   活跃单位 = tasks.active + bus.unread×0.15 + humanqueue.pending×0.3 + alerts.active×0.2
 * 空闲→0.55（安闲慢飞）；约 8 单位→2.2（繁忙星流）。
 * 场景每帧经 flybyDt() 向目标平滑趋近（~4s 过渡），无跳变。
 */

let target = 1;
let current = 1;
let lastSet = 0;

/** 指标轮询侧调用：写入目标强度（夹紧 0.4–2.5）。 */
export function setFlybyIntensity(v: number): void {
  const num = Number.isFinite(v) ? v : 1;
  target = Math.min(2.5, Math.max(0.4, num));
  lastSet = Date.now();
}

/**
 * 场景帧循环统一入口：替代裸 dt 做位移。
 * 指标源断流（>5 分钟无更新）时回落到 1，避免陈旧状态永久放大/缩小宇宙。
 */
export function flybyDt(dt: number): number {
  if (Date.now() - lastSet > 5 * 60_000) {
    target = 1;
  }
  current += (target - current) * Math.min(1, dt * 0.5);
  return dt * current;
}

/** 测试/调试：读当前平滑值与目标。 */
export function _flybyState(): { current: number; target: number } {
  return { current, target };
}

/** 由 metrics point 响应计算强度（纯函数，供单测）。 */
export function intensityFromMetrics(points: { metric: string; value: number | null }[]): number {
  const m = new Map<string, number>();
  for (const p of points) {
    if (p.value != null) m.set(p.metric, p.value);
  }
  const units =
    (m.get("tasks.active") ?? 0) +
    (m.get("bus.unread") ?? 0) * 0.15 +
    (m.get("humanqueue.pending") ?? 0) * 0.3 +
    (m.get("alerts.active") ?? 0) * 0.2;
  return 0.55 + Math.min(1.65, units / 8);
}
