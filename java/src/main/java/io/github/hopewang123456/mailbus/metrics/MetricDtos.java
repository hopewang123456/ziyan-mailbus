package io.github.hopewang123456.mailbus.metrics;

import java.util.List;
import java.util.Map;

public final class MetricDtos {

    private MetricDtos() {
    }

    public record MetricPointOut(String metric, Number value, String unit, String error) {
    }

    public record MetricSeriesOut(String metric, String granularity,
                                  List<Map<String, Object>> points) {
    }

    public record MetricQueryOut(List<MetricPointOut> points,
                                 List<MetricSeriesOut> series) {
    }

    public record MetricOverviewOut(String start, String end,
                                    List<MetricPointOut> cards,
                                    Map<String, Integer> totals) {
    }

    public record MetricTrendOut(String start, String end, String bucket,
                                 List<MetricSeriesOut> series) {
    }

    public record MetricBreakdownItemOut(String key, String label, Number value) {
    }

    public record MetricBreakdownOut(String start, String end, String metric,
                                     List<MetricBreakdownItemOut> items,
                                     Map<String, Object> extra) {
    }

    public record MetricRuleOut(String id, String metric, String op, double threshold,
                                String severity, boolean enabled, String note,
                                List<String> actions) {
    }

    public record MetricRuleListOut(List<MetricRuleOut> rules) {
    }

    public record MetricRulePageOut(List<MetricRuleOut> items, int total,
                                    int limit, int offset) {
    }

    public record MetricRuleUpdateIn(Map<String, Object> fields) {
        public MetricRuleUpdateIn {
            if (fields == null) {
                fields = Map.of();
            }
        }
    }

    public record MetricLayoutOut(List<String> hidden) {
    }

    public record MetricLayoutViewOut(MetricLayoutOut layout) {
    }

    public record MetricLayoutIn(List<String> hidden) {
        public MetricLayoutIn {
            if (hidden == null) {
                hidden = List.of();
            }
        }
    }

    public record MetricManifestOut(Map<String, Object> manifest) {
    }

    public record AlertOut(String id, String type, String severity, String agent,
                           String message, String ts) {
    }

    public record AlertListOut(List<AlertOut> alerts) {
    }

    public record ReviewerStatOut(int pass, int fail, int warn, int total) {
    }

    public record AuditStatsOut(int totalTasks, int auditedTasks, int pendingAuditTasks,
                                int passCount, int failCount, int warnCount,
                                Map<String, ReviewerStatOut> byReviewer) {
    }
}
