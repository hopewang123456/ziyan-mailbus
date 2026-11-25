import type { components } from "../contracts";

/**
 * Metric 域视图模型。
 */

export type MetricOverviewOut = components["schemas"]["MetricOverviewOut"];
export type MetricTrendOut = components["schemas"]["MetricTrendOut"];
export type MetricBreakdownOut = components["schemas"]["MetricBreakdownOut"];
export type MetricBreakdownItemOut = components["schemas"]["MetricBreakdownItemOut"];
export type MetricManifestOut = components["schemas"]["MetricManifestOut"];
export type MetricRuleOut = components["schemas"]["MetricRuleOut"];
export type MetricRulePageOut = components["schemas"]["MetricRulePageOut"];
export type MetricSeriesOut = components["schemas"]["MetricSeriesOut"];
export type MetricPointOut = components["schemas"]["mailbus__api__schemas__metrics__MetricPointOut"];

export type OverviewCard = MetricPointOut;
export type BreakdownRow = MetricBreakdownItemOut;
export type RuleRow = MetricRuleOut;
