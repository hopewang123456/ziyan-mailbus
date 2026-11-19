import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { ConsolePageHeader, ConsoleSection, ConsoleTable, ConsoleTag } from "../../components/console/ConsoleKit";
import { MetricCard } from "../../components/metrics/MetricCard";
import { getLang } from "../../lib/i18n";

/** 指标与报表管理（P3 / B4+B5）— 指标清单、告警规则编辑、大盘卡片可见性。 */

type Rule = {
  id: string;
  metric: string;
  op: string;
  threshold: number;
  severity: string;
  enabled: boolean;
  note?: string;
  actions?: string[];
};
type MetricEntry = { id: string; name?: { zh?: string }; unit?: string; description?: string };
type MetricPoint = { metric?: string; value?: number; unit?: string; error?: string };

export function ConsoleMetricsPage({ can }: { can: (capability: string) => boolean }) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [points, setPoints] = useState<MetricPoint[]>([]);
  const [hidden, setHidden] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const canManage = can("system_config");

  const load = async () => {
    setLoading(true);
    const [r, m, p, l] = await Promise.all([
      api<{ rules?: Rule[] }>("/api/metrics/rules"),
      api<{ manifest?: { metrics?: MetricEntry[] } }>("/api/metrics/manifest"),
      api<{ points?: MetricPoint[] }>("/api/metrics/query"),
      api<{ layout?: { hidden?: string[] } }>("/api/metrics/layout"),
    ]);
    setLoading(false);
    const errors: string[] = [];
    if (r.ok && r.data?.rules) setRules(r.data.rules);
    else if (!r.ok) errors.push(`规则：${r.error}`);
    if (m.ok && m.data?.manifest?.metrics) setMetrics(m.data.manifest.metrics);
    else if (!m.ok) errors.push(`清单：${m.error}`);
    if (p.ok && p.data?.points) setPoints(p.data.points);
    else if (!p.ok) errors.push(`查询：${p.error}`);
    if (l.ok && l.data?.layout) setHidden(l.data.layout.hidden || []);
    else if (!l.ok) errors.push(`布局：${l.error}`);
    setErr(errors.join("；"));
  };

  useEffect(() => {
    void load();
  }, []);

  async function patchRule(id: string, fields: Record<string, unknown>) {
    setErr("");
    setMsg("");
    const r = await api(`/api/metrics/rules/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ fields }),
    });
    if (r.ok) {
      setMsg(`规则 ${id} 已更新`);
      await load();
    } else setErr(r.error);
  }

  async function toggleHidden(metricId: string) {
    setErr("");
    setMsg("");
    const prev = hidden;
    const next = prev.includes(metricId) ? prev.filter((h) => h !== metricId) : [...prev, metricId];
    setHidden(next);
    const r = await api("/api/metrics/layout", { method: "PATCH", body: JSON.stringify({ hidden: next }) });
    if (r.ok) setMsg(next.includes(metricId) ? `${metricId} 已从大盘隐藏` : `${metricId} 已恢复显示`);
    else {
      setHidden(prev);
      setErr(r.error);
    }
  }

  const val = (id: string) => {
    const p = points.find((x) => x.metric === id);
    if (!p) return "—";
    if (p.error) return "查询失败";
    return p.value !== undefined ? p.value : "—";
  };

  return (
    <>
      <ConsolePageHeader
        title="指标与报表"
        description="指标口径 SoT（manifest）、告警规则（B5）、大盘布局（B4 dashboard as config）"
        actions={
          <button type="button" className="hud-btn text-xs" onClick={() => void load()}>
            刷新
          </button>
        }
      />
      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}
      {!canManage && (
        <p className="mb-3 text-[11px] text-amber-signal">
          规则与大盘布局为只读；修改需要 system_config。
        </p>
      )}

      <ConsoleSection title={`告警规则（${rules.length}）— 触发即写告警并通知子言`}>
        <ConsoleTable
          rows={rules}
          rowKey={(r) => r.id}
          loading={loading}
          empty="暂无告警规则"
          columns={[
            { key: "id", header: "规则", render: (r) => <span className="font-mono">{r.id}</span> },
            {
              key: "cond",
              header: "条件",
              render: (r) => (
                <span className="font-mono">
                  {r.metric} {r.op} {r.threshold}
                  <span className="ml-2 text-mute">(当前 {val(r.metric)})</span>
                </span>
              ),
            },
            {
              key: "sev",
              header: "级别",
              render: (r) => <ConsoleTag tone={r.severity === "critical" ? "danger" : "warn"}>{r.severity}</ConsoleTag>,
            },
            { key: "note", header: "说明", render: (r) => <span className="text-mute">{r.note || "—"}</span> },
            {
              key: "th",
              header: "阈值",
              render: (r) => (
                <input
                  type="number"
                  defaultValue={r.threshold}
                  disabled={!canManage}
                  className="w-20 rounded border border-rail bg-hull px-1.5 py-0.5 font-mono text-xs text-frost disabled:opacity-50"
                  onBlur={(e) => {
                    const v = Number(e.target.value);
                    if (!Number.isNaN(v) && v !== r.threshold) void patchRule(r.id, { threshold: v });
                  }}
                />
              ),
            },
            {
              key: "st",
              header: "状态",
              render: (r) => (
                <button
                  type="button"
                  disabled={!canManage}
                  onClick={() => void patchRule(r.id, { enabled: !r.enabled })}
                  className="rounded border border-rail px-2 py-0.5 text-[11px] text-mute hover:text-frost disabled:opacity-40"
                >
                  {r.enabled ? "停用" : "启用"}
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title="效率报表（P5 B 类 — 工单周期 / 人工介入，7 天口径）">
        <div className="grid gap-2.5 sm:grid-cols-2">
          <MetricCard entry={{ id: "tasks.cycle_avg_minutes", name: { zh: "工单平均周期（7天）" }, unit: "minutes" }} lang={getLang()} />
          <MetricCard entry={{ id: "tasks.interventions_week", name: { zh: "人工介入次数（7天）" }, unit: "count" }} lang={getLang()} />
        </div>
        <p className="mt-2 text-[11px] text-mute">
          口径：周期 = 终态任务 created_at→updated_at；介入 = human_gate.resolve 审批决策（SoT：metrics-manifest.json）
        </p>
      </ConsoleSection>

      <ConsoleSection title={`指标清单（${metrics.length}）— 管理大盘卡片可见性（B4）`}>
        <ConsoleTable
          rows={metrics}
          rowKey={(m) => m.id}
          loading={loading}
          empty="指标清单为空"
          columns={[
            { key: "id", header: "指标", render: (m) => <span className="font-mono">{m.id}</span> },
            { key: "name", header: "名称", render: (m) => m.name?.zh || "—" },
            {
              key: "desc",
              header: "口径",
              render: (m) => <span className="text-mute">{(m.description || "").slice(0, 50)}</span>,
            },
            { key: "val", header: "当前值", render: (m) => <span className="font-mono">{val(m.id)}</span> },
            {
              key: "vis",
              header: "大盘",
              render: (m) => (
                <button
                  type="button"
                  disabled={!canManage}
                  onClick={() => void toggleHidden(m.id)}
                  className={`rounded border px-2 py-0.5 text-[11px] disabled:opacity-40 ${
                    hidden.includes(m.id) ? "border-rail text-mute" : "border-mint/50 text-mint"
                  }`}
                >
                  {hidden.includes(m.id) ? "已隐藏" : "显示中"}
                </button>
              ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}
