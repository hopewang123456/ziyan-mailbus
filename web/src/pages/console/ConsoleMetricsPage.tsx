import { useCallback, useMemo, useState } from "react";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";
import {
  useMetricOverview,
  useTrend,
  useBreakdown,
  useMetricRules,
  useManifest,
} from "../../lib/metric/hooks";
import { metricExport, updateMetricRule } from "../../lib/metric/api";

type RangeKey = "7d" | "30d" | "custom";

const RANGE_PRESETS: Record<RangeKey, { days: number; bucket: string }> = {
  "7d": { days: 7, bucket: "day" },
  "30d": { days: 30, bucket: "day" },
  custom: { days: 7, bucket: "day" },
};

function buildRange(range: RangeKey, customFrom?: string | null, customTo?: string | null) {
  if (range === "custom" && customFrom && customTo) {
    return { from: customFrom, to: customTo };
  }
  const days = RANGE_PRESETS[range].days;
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

/** 画简易 SVG 折线图 — 接收 y 值数组，自动缩放 */
function LineChart({
  points,
  width = 480,
  height = 160,
}: {
  points: number[];
  width?: number;
  height?: number;
}) {
  if (points.length === 0) {
    return <p className="text-[11px] text-mute">暂无数据</p>;
  }
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const range = max - min || 1;
  const padX = 20;
  const padY = 12;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  const coords = points.map((v, i) => {
    const x = padX + (i / Math.max(points.length - 1, 1)) * plotW;
    const y = padY + plotH - ((v - min) / range) * plotH;
    return { x, y };
  });

  const pathD = coords
    .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ");

  const areaD = `${pathD} L${coords[coords.length - 1].x.toFixed(1)},${padY + plotH} L${coords[0].x.toFixed(1)},${padY + plotH} Z`;

  return (
    <svg width={width} height={height} className="max-w-full">
      {/* 网格 */}
      {[0, 0.25, 0.5, 0.75, 1].map((t) => {
        const y = padY + plotH * (1 - t);
        return (
          <line
            key={t}
            x1={padX}
            x2={width - padX}
            y1={y}
            y2={y}
            stroke="rgba(255,255,255,0.06)"
          />
        );
      })}
      {/* 面积 */}
      <path d={areaD} fill="rgba(0,229,180,0.12)" />
      {/* 折线 */}
      <path d={pathD} fill="none" stroke="#00e5b4" strokeWidth={1.5} />
      {/* 数据点 */}
      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r={2} fill="#00e5b4" />
      ))}
      {/* y 轴标签 */}
      <text x={4} y={padY + 4} fill="rgba(255,255,255,0.4)" fontSize="9">
        {max.toFixed(0)}
      </text>
      <text x={4} y={padY + plotH} fill="rgba(255,255,255,0.4)" fontSize="9">
        {min.toFixed(0)}
      </text>
    </svg>
  );
}

export function ConsoleMetricsPage({ can }: { can: (capability: string) => boolean }) {
  const canManage = can("system_config");

  // === 范围选择 ===
  const [range, setRange] = useState<RangeKey>("7d");
  const [customFrom, setCustomFrom] = useState<string | null>(null);
  const [customTo, setCustomTo] = useState<string | null>(null);

  const { from, to } = useMemo(
    () => buildRange(range, customFrom, customTo),
    [range, customFrom, customTo],
  );

  // === hook 调用 ===
  const overview = useMetricOverview({ from, to });
  const trend = useTrend({
    metric: ["messages.total"],
    from,
    to,
    bucket: RANGE_PRESETS[range].bucket,
  });
  const breakdown = useBreakdown({ metric: "messages.by_kind", from, to });
  const manifest = useManifest();
  const rules = useMetricRules({ limit: 100 });

  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState("");
  const [err, setErr] = useState("");

  const handleExport = useCallback(async () => {
    setExporting(true);
    setErr("");
    setExportMsg("");
    try {
      const r = await metricExport({ from, to });
      if (r.ok) setExportMsg("CSV 已下载");
      else setErr(r.error);
    } finally {
      setExporting(false);
    }
  }, [from, to]);

  const handleRuleToggle = useCallback(
    async (id: string, enabled: boolean) => {
      const r = await updateMetricRule(id, { fields: { enabled: !enabled } });
      if (!r.ok) setErr(`规则更新失败：${r.error}`);
      else rules.refresh();
    },
    [rules],
  );

  const trendPoints: number[] = useMemo(() => {
    const series = trend.data?.series?.[0];
    if (!series) return [];
    return series.points.map((p: any) => Number(p.value ?? 0));
  }, [trend.data]);

  return (
    <>
      <ConsolePageHeader
        title="指标中心"
        description="指标概览卡片、趋势 SVG、排行、CSV 导出 + 告警规则"
        actions={
          <>
            <div className="mr-3 flex items-center gap-1">
              {(Object.keys(RANGE_PRESETS) as RangeKey[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={`hud-btn text-xs ${range === key ? "text-mint" : ""}`}
                  onClick={() => setRange(key)}
                >
                  {key === "custom" ? "自定义" : key}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              onClick={handleExport}
              disabled={exporting}
            >
              {exporting ? "导出中…" : "CSV 导出"}
            </button>
          </>
        }
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {exportMsg && <p className="mb-3 text-xs text-mint">{exportMsg}</p>}

      {/* 自定义时间范围输入 */}
      {range === "custom" && (
        <div className="mb-4 flex items-end gap-2">
          <label className="text-[11px] text-mute">
            起始
            <input
              type="date"
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={customFrom ?? ""}
              onChange={(e) => setCustomFrom(e.target.value || null)}
            />
          </label>
          <label className="text-[11px] text-mute">
            结束
            <input
              type="date"
              className="mt-1 block rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              value={customTo ?? ""}
              onChange={(e) => setCustomTo(e.target.value || null)}
            />
          </label>
        </div>
      )}

      {/* === 概览卡片 === */}
      <ConsoleSection title={`指标概览（${from} → ${to}）`}>
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {overview.data?.cards && overview.data.cards.length > 0 ? (
            overview.data.cards.map((card, i) => (
              <div
                key={card.metric + i}
                className="rounded-lg border border-rail bg-hull/50 px-3 py-2.5"
              >
                <p className="text-[11px] text-mute">{card.metric}</p>
                <p className={`mt-1 font-mono text-lg ${card.error ? "text-flare" : "text-frost"}`}>
                  {card.error ?? card.value}
                  {card.unit !== "count" && <span className="ml-1 text-xs text-mute">{card.unit}</span>}
                </p>
              </div>
            ))
          ) : (
            <p className="col-span-full text-[11px] text-mute">
              {overview.loading ? "加载中…" : overview.error ?? "暂无指标数据"}
            </p>
          )}
        </div>
      </ConsoleSection>

      {/* === 趋势 SVG === */}
      <ConsoleSection title="消息总量趋势">
        <div className="rounded border border-rail bg-hull/50 p-2">
          {trend.loading ? (
            <p className="text-[11px] text-mute">加载中…</p>
          ) : trend.error ? (
            <p className="text-xs text-flare">{trend.error}</p>
          ) : (
            <LineChart points={trendPoints} />
          )}
        </div>
      </ConsoleSection>

      {/* === 排行 === */}
      <ConsoleSection title="消息类型排行">
        <ConsoleTable
          rows={breakdown.data?.items ?? []}
          rowKey={(row: any) => row.key}
          loading={breakdown.loading}
          empty="暂无排行数据"
          columns={[
            {
              key: "label",
              header: "类型",
              render: (row: any) => <ConsoleTag>{row.label || row.key}</ConsoleTag>,
            },
            {
              key: "value",
              header: "数量",
              render: (row: any) => <span className="font-mono">{row.value}</span>,
            },
            {
              key: "bar",
              header: "",
              render: (row: any) => {
                const max = Math.max(
                  ...((breakdown.data?.items ?? []) as any[]).map((i) => i.value),
                  1,
                );
                const width = Math.round((row.value / max) * 100);
                return (
                  <div className="h-1.5 w-full bg-rail">
                    <div className="h-full bg-mint" style={{ width: `${width}%` }} />
                  </div>
                );
              },
            },
          ]}
        />
      </ConsoleSection>

      {/* === 告警规则 === */}
      <ConsoleSection title={`告警规则（${rules.items.length}）`}>
        <ConsoleTable
          rows={rules.items as any[]}
          rowKey={(row: any) => row.id}
          loading={rules.loading}
          empty="暂无告警规则"
          columns={[
            { key: "id", header: "规则", render: (row: any) => <span className="font-mono">{row.id}</span> },
            {
              key: "cond",
              header: "条件",
              render: (row: any) => (
                <span className="font-mono">
                  {row.metric} {row.op} {row.threshold}
                </span>
              ),
            },
            {
              key: "sev",
              header: "级别",
              render: (row: any) => (
                <ConsoleTag tone={row.severity === "critical" ? "danger" : "warn"}>
                  {row.severity}
                </ConsoleTag>
              ),
            },
            {
              key: "note",
              header: "说明",
              render: (row: any) => <span className="text-mute">{row.note || "—"}</span>,
            },
            {
              key: "st",
              header: "状态",
              render: (row: any) => (
                <button
                  type="button"
                  disabled={!canManage}
                  onClick={() => void handleRuleToggle(row.id, row.enabled)}
                  className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                >
                  {row.enabled ? "停用" : "启用"}
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>

      {/* === 指标清单 === */}
      <ConsoleSection title="指标口径清单（manifest）">
        {manifest.data?.manifest && (
          <pre className="max-h-64 overflow-auto rounded border border-rail bg-hull px-2 py-1 text-[11px] text-mute font-mono">
            {JSON.stringify(manifest.data.manifest, null, 2)}
          </pre>
        )}
      </ConsoleSection>
    </>
  );
}
