/** 展示层统一格式化：JSON 时间一律 ISO 8601 UTC，展示时转本地。 */

function parse(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

const pad = (value: number) => String(value).padStart(2, "0");

export function formatDateTime(value: string | number | Date | null | undefined): string {
  const date = parse(value);
  if (!date) return "—";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function formatDate(value: string | number | Date | null | undefined): string {
  const date = parse(value);
  if (!date) return "—";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatTime(value: string | number | Date | null | undefined): string {
  const date = parse(value);
  if (!date) return "—";
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

const UNITS: Array<[number, string]> = [
  [365 * 24 * 3600, "年前"],
  [30 * 24 * 3600, "个月前"],
  [7 * 24 * 3600, "周前"],
  [24 * 3600, "天前"],
  [3600, "小时前"],
  [60, "分钟前"],
  [1, "秒前"],
];

export function formatRelative(
  value: string | number | Date | null | undefined,
  now: number = Date.now(),
): string {
  const date = parse(value);
  if (!date) return "—";
  const diff = Math.floor((now - date.getTime()) / 1000);
  if (diff < 0) return formatDateTime(date);
  if (diff < 10) return "刚刚";
  for (const [seconds, label] of UNITS) {
    if (diff >= seconds) return `${Math.floor(diff / seconds)}${label}`;
  }
  return "刚刚";
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatBytes(value: number | null | undefined): string {
  if (!value || value < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

/** 状态文案统一入口：未登记的状态原样显示，避免吞掉后端新值。 */
export function statusLabel(state: string | null | undefined, labels: Record<string, string>): string {
  if (!state) return "—";
  return labels[state] ?? state;
}
