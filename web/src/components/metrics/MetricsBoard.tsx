/** 指标大盘（P2 A 期实时大盘，B7 question→dashboard）：manifest 驱动的卡片网格 */
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { MetricCard, type MetricEntry } from "./MetricCard";
import { getLang } from "../../lib/i18n";

export function MetricsBoard() {
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [err, setErr] = useState("");
  const [updatedAt] = useState("");
  // B4 dashboard as config：管理中心配置的 hidden 清单在此生效
  const [hidden, setHidden] = useState<string[]>([]);

  useEffect(() => {
    void api<{ manifest?: { metrics?: MetricEntry[] } }>("/api/metrics/manifest").then((r) => {
      if (r.ok && r.data?.manifest?.metrics) setMetrics(r.data.manifest.metrics);
      else if (!r.ok) setErr(r.error);
    });
    void api<{ layout?: { hidden?: string[] } }>("/api/metrics/layout").then((r) => {
      if (r.ok && r.data?.layout?.hidden) setHidden(r.data.layout.hidden);
    });
  }, []);

  return (
    <div className="space-y-3" data-surface="fleet">
      <header className="flex items-end justify-between gap-2">
        <div>
          <p className="hud-label">Metrics</p>
          <h2 className="mt-1 font-display text-lg text-frost">指标大盘</h2>
        </div>
        <span className="font-mono text-[10px] text-mute">
          {updatedAt ? `刷新于 ${updatedAt}` : "30s 自动刷新"} · 口径 SoT: metrics-manifest.json
        </span>
      </header>
      {err && <p className="text-xs text-flare">{err}</p>}
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {metrics
          .filter((m) => !hidden.includes(m.id))
          .map((m) => (
            <MetricCard key={m.id} entry={m} lang={getLang()} />
          ))}
      </div>
      {metrics.length === 0 && !err && <p className="text-xs text-mute">加载 manifest 中…</p>}
    </div>
  );
}
