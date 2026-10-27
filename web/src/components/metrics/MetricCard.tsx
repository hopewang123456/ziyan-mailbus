/** 单指标卡（P2 B7 question 模式）：值 + 单位 + 迷你趋势（1h 时序 sparkline） */
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { formatValue, sparklinePath } from "./format";

export type MetricEntry = {
  id: string;
  name?: { zh?: string; en?: string };
  unit?: string;
};

export function MetricCard({ entry, lang }: { entry: MetricEntry; lang: "zh" | "en" }) {
  const [value, setValue] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [trend, setTrend] = useState<number[]>([]);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const r = await api<{ points?: Array<{ value?: number; error?: string }> }>(
        `/api/metrics/query?metric=${encodeURIComponent(entry.id)}`,
      );
      if (!alive) return;
      const p = r.ok && r.data ? r.data.points?.[0] : undefined;
      if (r.ok && p && p.error === undefined) {
        setValue(p.value ?? null);
        setError("");
      } else {
        setError((p?.error as string) || ("error" in r ? String(r.error) : "") || "unavailable");
      }
      const w = await api<{ series?: Array<{ points?: Array<{ value?: number }> }> }>(
        `/api/metrics/query?metric=${encodeURIComponent(entry.id)}&granularity=1h&hours=24`,
      );
      if (alive && w.ok && w.data) {
        setTrend((w.data.series?.[0]?.points || []).map((x) => x.value ?? 0));
      }
    };
    void tick();
    const timer = window.setInterval(tick, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [entry.id]);

  const label = (lang === "en" ? entry.name?.en : entry.name?.zh) || entry.id;
  const danger = entry.id.includes("fail") || entry.id.includes("alert");

  return (
    <div className="soft-inset flex flex-col gap-1 rounded-lg px-3 py-2.5" data-testid={`metric-${entry.id}`}>
      <span className="text-[11px] leading-tight text-mute">{label}</span>
      <div className="flex items-baseline gap-1">
        {error ? (
          <span className="font-mono text-sm text-flare/80">{error.slice(0, 22)}</span>
        ) : (
          <span className={`font-mono text-xl ${danger && (value ?? 0) > 0 ? "text-flare" : "text-frost"}`}>
            {value === null ? "…" : formatValue(value)}
          </span>
        )}
        {!error && <span className="text-[10px] text-mute">{entry.unit === "count" ? "" : entry.unit}</span>}
      </div>
      <Sparkline points={trend} danger={danger && (value ?? 0) > 0} />
    </div>
  );
}

function Sparkline({ points, danger }: { points: number[]; danger?: boolean }) {
  if (points.length < 2) {
    return <div className="h-4" aria-hidden />;
  }
  const w = 100;
  const h = 16;
  const path = sparklinePath(points);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-4 w-full" preserveAspectRatio="none" aria-hidden>
      <polyline
        points={path}
        fill="none"
        strokeWidth="1.5"
        className={danger ? "stroke-flare" : "stroke-mint"}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

