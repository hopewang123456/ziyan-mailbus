import { api, downloadFile } from "../api";
import type { components } from "../contracts";

/**
 * Metric 域唯一 API 落点。
 * 类型全部来自 contracts.ts 生成；禁止手写 DTO。
 */

type MetricOverviewOut = components["schemas"]["MetricOverviewOut"];
type MetricTrendOut = components["schemas"]["MetricTrendOut"];
type MetricBreakdownOut = components["schemas"]["MetricBreakdownOut"];
type MetricManifestOut = components["schemas"]["MetricManifestOut"];
type MetricRuleOut = components["schemas"]["MetricRuleOut"];
type MetricRulePageOut = components["schemas"]["MetricRulePageOut"];
type MetricRuleUpdateIn = components["schemas"]["MetricRuleUpdateIn"];

// === 概览 / 趋势 / 排行 / 清单 ===

export function metricOverview(query?: { from?: string | null; to?: string | null }) {
  const params = new URLSearchParams();
  if (query?.from) params.set("from", query.from);
  if (query?.to) params.set("to", query.to);
  const q = params.toString();
  return api<MetricOverviewOut>(q ? `/api/metrics/overview?${q}` : "/api/metrics/overview");
}

export function metricTrend(query: { metric?: string[] | null; from?: string | null; to?: string | null; bucket?: string }) {
  const params = new URLSearchParams();
  if (query.metric?.length) {
    for (const m of query.metric) params.append("metric", m);
  }
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  if (query.bucket) params.set("bucket", query.bucket);
  const q = params.toString();
  return api<MetricTrendOut>(q ? `/api/metrics/trend?${q}` : "/api/metrics/trend");
}

export function metricBreakdown(query: { metric?: string | null; from?: string | null; to?: string | null }) {
  const params = new URLSearchParams();
  if (query.metric) params.set("metric", query.metric);
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  const q = params.toString();
  return api<MetricBreakdownOut>(q ? `/api/metrics/breakdown?${q}` : "/api/metrics/breakdown");
}

export function metricManifest() {
  return api<MetricManifestOut>("/api/metrics/manifest");
}

export function metricExport(query: { metric?: string[] | null; from?: string | null; to?: string | null }) {
  const params = new URLSearchParams();
  if (query.metric?.length) {
    for (const m of query.metric) params.append("metric", m);
  }
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  const q = params.toString();
  const url = q ? `/api/metrics/export?${q}` : "/api/metrics/export";
  const filename = `metrics-export-${Date.now()}.csv`;
  return downloadFile(url, { filename });
}

// === 告警规则 CRUD ===

export function listMetricRules(query?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (query?.limit !== undefined) params.set("limit", String(query.limit));
  if (query?.offset !== undefined) params.set("offset", String(query.offset));
  const q = params.toString();
  return api<MetricRulePageOut>(q ? `/api/metrics/rules?${q}` : "/api/metrics/rules");
}

export function getMetricRule(ruleId: string) {
  return api<MetricRuleOut>(`/api/metrics/rules/${encodeURIComponent(ruleId)}`);
}

export function updateMetricRule(ruleId: string, body: MetricRuleUpdateIn) {
  return api<MetricRuleOut>(`/api/metrics/rules/${encodeURIComponent(ruleId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
