package io.github.hopewang123456.mailbus.metrics;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.observability.ObservabilityDtos;
import io.github.hopewang123456.mailbus.observability.OverviewService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.MathContext;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
public class MetricsService {

    private static final Set<String> UNCOLLECTED = Set.of(
            "tokens.today_estimated",
            "tasks.cycle_avg_minutes",
            "tasks.interventions_week",
            "bus.unread");
    private static final Set<String> PATCHABLE = Set.of(
            "metric", "op", "threshold", "severity", "enabled", "note", "actions");
    private static final Set<String> OPERATORS = Set.of(">", ">=", "<", "<=", "=", "!=");
    private static final Set<String> SEVERITIES = Set.of("info", "warn", "critical");
    private static final int MAX_NOTE = 200;

    private final JdbcTemplate jdbc;
    private final Outbox outbox;
    private final ObjectMapper objectMapper;
    private final OverviewService overview;
    private final AppProperties properties;

    public MetricsService(JdbcTemplate jdbc, Outbox outbox, ObjectMapper objectMapper,
                          OverviewService overview, AppProperties properties) {
        this.jdbc = jdbc;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
        this.overview = overview;
        this.properties = properties;
    }

    public Map<String, Object> manifest() {
        for (Path path : manifestCandidates()) {
            if (!Files.isRegularFile(path)) {
                continue;
            }
            try {
                Map<String, Object> data = objectMapper.readValue(path.toFile(),
                        new TypeReference<Map<String, Object>>() {
                        });
                return data == null ? Map.of() : data;
            } catch (Exception ignored) {
                // 与 Python 一致：读不到就当清单不可用
            }
        }
        Map<String, Object> fallback = new LinkedHashMap<>();
        fallback.put("metrics", List.of());
        fallback.put("note", "指标清单不可用：" + properties.metricsManifestFile());
        return fallback;
    }

    public MetricDtos.MetricQueryOut query(List<String> metrics, String granularity, int hours) {
        Map<String, Map<String, Object>> catalog = catalog();
        Map<String, ObservabilityDtos.MetricPoint> current = currentMetrics();
        List<String> ids = metrics == null || metrics.isEmpty()
                ? new ArrayList<>(catalog.keySet())
                : metrics;
        int alertCount = alerts().size();
        List<MetricDtos.MetricPointOut> points = new ArrayList<>();
        for (String metric : ids) {
            points.add(point(metric, catalog.get(metric), current, alertCount));
        }
        List<MetricDtos.MetricSeriesOut> series = new ArrayList<>();
        if (metrics != null && !metrics.isEmpty()) {
            for (String metric : ids) {
                series.add(new MetricDtos.MetricSeriesOut(metric, granularity, List.of()));
            }
        }
        return new MetricDtos.MetricQueryOut(points, series);
    }

    public List<MetricDtos.AlertOut> alerts() {
        Map<String, Number> current = new LinkedHashMap<>();
        for (ObservabilityDtos.MetricPoint point : overview.get().metrics()) {
            current.put(point.metric(), point.value());
        }
        List<MetricDtos.AlertOut> alerts = new ArrayList<>();
        for (RuleRow rule : rules()) {
            if (!rule.enabled() || !current.containsKey(rule.metric())) {
                continue;
            }
            double value = current.get(rule.metric()).doubleValue();
            if (!triggered(value, rule.op(), rule.threshold())) {
                continue;
            }
            String message = rule.note() == null || rule.note().isBlank()
                    ? rule.metric() + " " + rule.op() + " " + formatG(rule.threshold())
                    + "（当前 " + formatG(value) + "）"
                    : rule.note();
            alerts.add(new MetricDtos.AlertOut(rule.ruleId(), rule.metric(), rule.severity(),
                    "", message, Instant.now().toString()));
        }
        return alerts;
    }

    public List<MetricDtos.MetricRuleOut> listRules() {
        return rules().stream().map(this::toOut).toList();
    }

    @Transactional
    public MetricDtos.MetricRuleOut updateRule(Actor actor, String ruleId,
                                               Map<String, Object> changes) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("metric"));
        Map<String, Object> fields = changes == null ? Map.of() : changes;
        List<String> unknown = fields.keySet().stream()
                .filter(key -> !PATCHABLE.contains(key)).sorted().toList();
        if (!unknown.isEmpty()) {
            throw ApiException.conflict("invalid_state", "不允许修改字段：" + String.join(", ", unknown));
        }
        RuleRow current = findRule(ruleId)
                .orElseThrow(() -> ApiException.notFound("告警规则不存在"));
        String metric = current.metric();
        String op = current.op();
        double threshold = current.threshold();
        String severity = current.severity();
        boolean enabled = current.enabled();
        String note = current.note();
        List<String> actions = current.actions();
        List<String> touched = new ArrayList<>();
        if (fields.containsKey("metric")) {
            metric = text(fields.get("metric"), "指标 id", 64, false);
            touched.add("metric");
        }
        if (fields.containsKey("op")) {
            String value = text(fields.get("op"), "操作符", 2, false);
            if (!OPERATORS.contains(value)) {
                throw ApiException.conflict("invalid_state", "操作符只支持 > >= < <= = !=");
            }
            op = value;
            touched.add("op");
        }
        if (fields.containsKey("threshold")) {
            threshold = number(fields.get("threshold"));
            touched.add("threshold");
        }
        if (fields.containsKey("severity")) {
            String value = text(fields.get("severity"), "级别", 16, false);
            if (!SEVERITIES.contains(value)) {
                throw ApiException.conflict("invalid_state", "级别只支持 info / warn / critical");
            }
            severity = value;
            touched.add("severity");
        }
        if (fields.containsKey("enabled")) {
            enabled = truthy(fields.get("enabled"));
            touched.add("enabled");
        }
        if (fields.containsKey("note")) {
            note = text(fields.get("note"), "说明", MAX_NOTE, true);
            touched.add("note");
        }
        if (fields.containsKey("actions")) {
            actions = actions(fields.get("actions"));
            touched.add("actions");
        }
        if (metric.equals(current.metric()) && op.equals(current.op())
                && threshold == current.threshold() && severity.equals(current.severity())
                && enabled == current.enabled() && note.equals(current.note())
                && actions.equals(current.actions())) {
            return toOut(current);
        }
        RuleRow updated = new RuleRow(ruleId, metric, op, threshold, severity, enabled,
                note, actions);
        jdbc.update("""
                INSERT INTO metrics_rules
                    (rule_id, metric, op, threshold, severity, enabled, note, actions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (rule_id) DO UPDATE SET
                    metric = excluded.metric, op = excluded.op,
                    threshold = excluded.threshold, severity = excluded.severity,
                    enabled = excluded.enabled, note = excluded.note,
                    actions = excluded.actions
                """, updated.ruleId(), updated.metric(), updated.op(), updated.threshold(),
                updated.severity(), updated.enabled() ? 1 : 0, updated.note(),
                actionsJson(updated.actions()));
        List<String> sorted = touched.stream().sorted().toList();
        outbox.enqueue("metrics.rule_updated",
                Map.of("rule_id", ruleId, "fields", sorted));
        return toOut(updated);
    }

    public MetricDtos.MetricLayoutViewOut layout() {
        return new MetricDtos.MetricLayoutViewOut(
                new MetricDtos.MetricLayoutOut(hidden()));
    }

    @Transactional
    public MetricDtos.MetricLayoutViewOut updateLayout(Actor actor, List<String> hidden) {
        Authz.ensureAllowed(actor, Authz.SYSTEM_CONFIG, Authz.Resource.of("metric"));
        List<String> requested = hidden == null ? List.of() : hidden;
        Set<String> values = new LinkedHashSet<>();
        for (String item : requested) {
            if (item == null) {
                throw ApiException.conflict("invalid_state", "hidden 必须是字符串数组");
            }
            String text = item.strip();
            if (!text.isEmpty()) {
                values.add(text);
            }
        }
        List<String> current = hidden();
        List<String> updated = new ArrayList<>(values);
        if (!updated.equals(current)) {
            jdbc.update("""
                    INSERT INTO metrics_layout (id, hidden) VALUES (1, ?)
                    ON CONFLICT (id) DO UPDATE SET hidden = excluded.hidden
                    """, json(updated));
            outbox.enqueue("metrics.layout_updated", Map.of("hidden", updated));
        }
        return new MetricDtos.MetricLayoutViewOut(
                new MetricDtos.MetricLayoutOut(updated));
    }

    // ---------- helpers ----------

    private Map<String, Map<String, Object>> catalog() {
        Map<String, Map<String, Object>> result = new LinkedHashMap<>();
        Object metrics = manifest().get("metrics");
        if (metrics instanceof List<?> items) {
            for (Object item : items) {
                if (item instanceof Map<?, ?> entry && entry.get("id") != null) {
                    Map<String, Object> casted = new LinkedHashMap<>();
                    entry.forEach((key, value) -> casted.put(String.valueOf(key), value));
                    result.put(String.valueOf(entry.get("id")), casted);
                }
            }
        }
        return result;
    }

    private Map<String, ObservabilityDtos.MetricPoint> currentMetrics() {
        Map<String, ObservabilityDtos.MetricPoint> current = new LinkedHashMap<>();
        for (ObservabilityDtos.MetricPoint point : overview.get().metrics()) {
            current.put(point.metric(), point);
        }
        return current;
    }

    private MetricDtos.MetricPointOut point(String metric, Map<String, Object> entry,
                                            Map<String, ObservabilityDtos.MetricPoint> current,
                                            int alertCount) {
        String unit = entry != null && entry.get("unit") != null
                ? String.valueOf(entry.get("unit")) : "count";
        if (current.containsKey(metric)) {
            return new MetricDtos.MetricPointOut(metric, current.get(metric).value(), unit, null);
        }
        if ("alerts.active".equals(metric)) {
            return new MetricDtos.MetricPointOut(metric, alertCount, unit, null);
        }
        if (UNCOLLECTED.contains(metric)) {
            return new MetricDtos.MetricPointOut(metric, 0, unit, "未开始采集");
        }
        if (entry != null) {
            return new MetricDtos.MetricPointOut(metric, 0, unit, "指标未接入");
        }
        return new MetricDtos.MetricPointOut(metric, 0, unit, "未知指标");
    }

    private List<RuleRow> rules() {
        return jdbc.query("SELECT * FROM metrics_rules ORDER BY rule_id",
                (row, index) -> new RuleRow(row.getString("rule_id"),
                        row.getString("metric"), row.getString("op"),
                        row.getDouble("threshold"), row.getString("severity"),
                        row.getInt("enabled") == 1, row.getString("note"),
                        actionsOf(row.getString("actions"))));
    }

    private java.util.Optional<RuleRow> findRule(String ruleId) {
        return jdbc.query("SELECT * FROM metrics_rules WHERE rule_id = ?",
                (row, index) -> new RuleRow(row.getString("rule_id"),
                        row.getString("metric"), row.getString("op"),
                        row.getDouble("threshold"), row.getString("severity"),
                        row.getInt("enabled") == 1, row.getString("note"),
                        actionsOf(row.getString("actions"))), ruleId)
                .stream().findFirst();
    }

    private List<String> hidden() {
        List<String> rows = jdbc.query("SELECT hidden FROM metrics_layout WHERE id = 1",
                (row, index) -> row.getString("hidden"));
        if (rows.isEmpty() || rows.get(0) == null) {
            return List.of();
        }
        try {
            List<String> values = objectMapper.readValue(rows.get(0),
                    new TypeReference<List<String>>() {
                    });
            return values == null ? List.of() : values;
        } catch (Exception exception) {
            return List.of();
        }
    }

    private MetricDtos.MetricRuleOut toOut(RuleRow rule) {
        return new MetricDtos.MetricRuleOut(rule.ruleId(), rule.metric(), rule.op(),
                rule.threshold(), rule.severity(), rule.enabled(), rule.note(),
                rule.actions());
    }

    private List<Path> manifestCandidates() {
        return List.of(properties.metricsManifestFile(),
                Path.of("shared", "config", "mailbus", "metrics-manifest.json"),
                Path.of("..", "shared", "config", "mailbus", "metrics-manifest.json"));
    }

    private List<String> actionsOf(String value) {
        if (value == null || value.isBlank()) {
            return List.of();
        }
        try {
            List<String> items = objectMapper.readValue(value,
                    new TypeReference<List<String>>() {
                    });
            return items == null ? List.of() : items;
        } catch (Exception exception) {
            return List.of();
        }
    }

    private List<String> actions(Object value) {
        if (!(value instanceof List<?> items)) {
            throw ApiException.conflict("invalid_state", "actions 必须是字符串数组");
        }
        List<String> result = new ArrayList<>();
        for (Object item : items) {
            if (!(item instanceof String text)) {
                throw ApiException.conflict("invalid_state", "actions 必须是字符串数组");
            }
            if (!text.isBlank()) {
                result.add(text.strip());
            }
        }
        return result;
    }

    private String text(Object value, String label, int limit, boolean allowEmpty) {
        if (!(value instanceof String raw)) {
            throw ApiException.conflict("invalid_state", label + "必须是字符串");
        }
        String text = raw.strip();
        if (text.isEmpty() && !allowEmpty) {
            throw ApiException.conflict("invalid_state", label + "不能为空");
        }
        if (text.length() > limit) {
            throw ApiException.conflict("invalid_state",
                    label + "不能超过 " + limit + " 个字符");
        }
        return text;
    }

    private double number(Object value) {
        if (value instanceof Boolean || !(value instanceof Number number)) {
            throw ApiException.conflict("invalid_state", "阈值必须是数字");
        }
        return number.doubleValue();
    }

    private boolean truthy(Object value) {
        if (value == null || Boolean.FALSE.equals(value)) {
            return false;
        }
        if (value instanceof String text) {
            return !text.isEmpty();
        }
        if (value instanceof Number number) {
            return number.doubleValue() != 0;
        }
        return true;
    }

    private boolean triggered(double value, String op, double threshold) {
        return switch (op) {
            case ">" -> value > threshold;
            case ">=" -> value >= threshold;
            case "<" -> value < threshold;
            case "<=" -> value <= threshold;
            case "=" -> value == threshold;
            default -> value != threshold;
        };
    }

    /** 近似 Python 的 ``{value:g}``：整数不带小数点，其余最多 6 位有效数字。 */
    private String formatG(double value) {
        if (value == Math.rint(value) && Math.abs(value) < 1_000_000) {
            return String.valueOf((long) value);
        }
        return new BigDecimal(value).round(new MathContext(6))
                .stripTrailingZeros().toPlainString();
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            throw new IllegalStateException("JSON 序列化失败", exception);
        }
    }

    private String actionsJson(List<String> actions) {
        return json(actions);
    }

    private record RuleRow(String ruleId, String metric, String op, double threshold,
                           String severity, boolean enabled, String note,
                           List<String> actions) {
    }
}
