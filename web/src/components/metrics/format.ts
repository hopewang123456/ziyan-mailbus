/** 指标卡纯逻辑（提取以便单测） */
export function formatValue(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** sparkline 的 points→SVG path 归一化（0-100 x 0-16 视窗） */
export function sparklinePath(points: number[], w = 100, h = 16): string {
  if (points.length < 2) return "";
  const max = Math.max(...points);
  const min = Math.min(...points);
  const span = max - min || 1;
  return points
    .map((v, i) => `${(i / (points.length - 1)) * w},${h - ((v - min) / span) * (h - 2) - 1}`)
    .join(" ");
}
