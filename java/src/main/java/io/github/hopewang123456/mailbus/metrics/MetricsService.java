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
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAccessor;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

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

    public MetricDtos.MetricOverviewOut overviewReport(Actor actor, String from, String to) {
        Range range = range(from, to);
        List<String> owners = visibleOwners(actor);
        TaskSummary summary = taskSummary(range.start(), range.end(), owners);
        int escalations = escalations(range.start(), range.end(), owners);
        int online = onlineAgents(epochNow() - 180.0);
        Map<String, Integer> totals = new LinkedHashMap<>();
        totals.put("total", summary.total());
        totals.put("done", summary.done());
        totals.put("failed", summary.failed());
        totals.put("cancelled", summary.cancelled());
        totals.put("active", summary.active());
        totals.put("queued", summary.queued());
        return new MetricDtos.MetricOverviewOut(iso(range.start()), iso(range.end()),
                cards(summary, escalations, online), totals);
    }

    public MetricDtos.MetricTrendOut trendReport(Actor actor, List<String> metrics,
                                                  String from, String to, String bucket) {
        Range range = range(from, to);
        int step = bucketSeconds(bucket);
        List<String> ids = metrics == null || metrics.isEmpty()
                ? List.of("tasks.created", "tasks.completed") : metrics;
        Set<String> unknown = new TreeSet<>(ids);
        unknown.removeAll(Set.of("tasks.created", "tasks.completed"));
        if (!unknown.isEmpty()) {
            throw unprocessable("不支持的趋势指标：" + String.join(", ", unknown));
        }
        List<String> owners = visibleOwners(actor);
        List<TimelineRow> timeline = taskTimeline(range.start(), range.end(), owners);
        List<MetricDtos.MetricSeriesOut> series = new ArrayList<>();
        for (String metric : ids) {
            series.add(new MetricDtos.MetricSeriesOut(metric, bucket,
                    points(timeline, metric, range.start(), range.end(), step)));
        }
        return new MetricDtos.MetricTrendOut(iso(range.start()), iso(range.end()),
                bucket, series);
    }

    public MetricDtos.MetricBreakdownOut breakdownReport(Actor actor, String metric,
                                                          String from, String to) {
        String selected = metric == null || metric.isEmpty()
                ? "workflow_completion_rate" : metric;
        Range range = range(from, to);
        List<String> owners = visibleOwners(actor);
        List<BreakdownEntry> entries;
        if (Set.of("workflow_completion_rate", "workflow_avg_duration").contains(selected)) {
            entries = workflowItems(selected, range.start(), range.end(), owners);
        } else if (Set.of("agent_load", "agent_failure_rate").contains(selected)) {
            entries = agentItems(selected, range.start(), range.end(), owners);
        } else {
            throw unprocessable("不支持的排行指标：" + selected);
        }
        Map<String, Object> extras = new LinkedHashMap<>();
        for (BreakdownEntry entry : entries) {
            if (!entry.extra().isEmpty()) {
                extras.put(entry.key(), entry.extra());
            }
        }
        List<BreakdownEntry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparingDouble(
                (BreakdownEntry entry) -> entry.value().doubleValue()).reversed());
        List<MetricDtos.MetricBreakdownItemOut> items = sorted.stream()
                .map(entry -> new MetricDtos.MetricBreakdownItemOut(
                        entry.key(), entry.label(), entry.value()))
                .toList();
        return new MetricDtos.MetricBreakdownOut(iso(range.start()), iso(range.end()),
                selected, items, extras);
    }

    public String exportCsv(Actor actor, String from, String to) {
        MetricDtos.MetricOverviewOut overview = overviewReport(actor, from, to);
        MetricDtos.MetricBreakdownOut workflows = breakdownReport(
                actor, "workflow_completion_rate", from, to);
        MetricDtos.MetricBreakdownOut agents = breakdownReport(actor, "agent_load", from, to);
        StringBuilder buffer = new StringBuilder("\uFEFF");
        csvRow(buffer, "section", "key", "label", "metric", "value", "unit");
        for (MetricDtos.MetricPointOut card : overview.cards()) {
            csvRow(buffer, "card", card.metric(), "", card.metric(), card.value(), card.unit());
        }
        csvBreakdownRows(buffer, "workflow", workflows);
        csvBreakdownRows(buffer, "agent", agents);
        return buffer.toString();
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

    public MetricDtos.MetricRuleOut getRule(String ruleId) {
        return findRule(ruleId).map(this::toOut)
                .orElseThrow(() -> ApiException.notFound("告警规则不存在"));
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

    /** global 全量（null）；team 本队含本人；self 仅本人。 */
    private List<String> visibleOwners(Actor actor) {
        if ("global".equals(actor.dataScope())) {
            return null;
        }
        if ("self".equals(actor.dataScope())) {
            return List.of(actor.employeeId());
        }
        Set<String> owners = new TreeSet<>();
        List<Map<String, Object>> employees = jdbc.queryForList(
                "SELECT employee_id, team_id FROM identity_employees"
                        + " WHERE deleted_at IS NULL ORDER BY created_at");
        for (Map<String, Object> employee : employees) {
            if (Objects.equals(employee.get("team_id"), actor.teamId())) {
                owners.add(String.valueOf(employee.get("employee_id")));
            }
        }
        owners.add(actor.employeeId());
        return new ArrayList<>(owners);
    }

    private TaskSummary taskSummary(double start, double end, List<String> owners) {
        OwnerScope scope = ownerScope(owners, "owner_id");
        String sql = """
                SELECT COUNT(*) AS total,
                 SUM(CASE WHEN state = 'queued' THEN 1 ELSE 0 END) AS queued,
                 SUM(CASE WHEN state IN ('queued','running','blocked') THEN 1 ELSE 0 END) AS active,
                 SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) AS done,
                 SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) AS failed,
                 SUM(CASE WHEN state = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
                 AVG(CASE WHEN state = 'done' THEN updated_at - created_at END) AS avg_done
                 FROM task_tasks WHERE created_at BETWEEN ? AND ?
                """ + scope.sql();
        return jdbc.queryForObject(sql, (row, index) -> new TaskSummary(
                        row.getInt("total"), row.getInt("queued"), row.getInt("active"),
                        row.getInt("done"), row.getInt("failed"), row.getInt("cancelled"),
                        round1(row.getDouble("avg_done") / 60.0)),
                params(scope, start, end));
    }

    private int escalations(double start, double end, List<String> owners) {
        OwnerScope scope = ownerScope(owners, "t.owner_id");
        String sql = "SELECT COUNT(*) AS total FROM task_escalations e"
                + " JOIN task_tasks t ON t.task_id = e.task_id"
                + " WHERE t.created_at BETWEEN ? AND ?" + scope.sql();
        Integer count = jdbc.queryForObject(sql, Integer.class, params(scope, start, end));
        return count == null ? 0 : count;
    }

    private int onlineAgents(double cutoff) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) AS total FROM agents"
                + " WHERE enabled = 1 AND deleted_at IS NULL AND last_seen_at >= ?",
                Integer.class, cutoff);
        return count == null ? 0 : count;
    }

    private List<TimelineRow> taskTimeline(double start, double end, List<String> owners) {
        OwnerScope scope = ownerScope(owners, "owner_id");
        String sql = "SELECT created_at, updated_at, state FROM task_tasks"
                + " WHERE (created_at BETWEEN ? AND ?"
                + " OR (state = 'done' AND updated_at BETWEEN ? AND ?))" + scope.sql();
        return jdbc.query(sql, (row, index) -> new TimelineRow(
                        row.getDouble("created_at"), row.getDouble("updated_at"),
                        row.getString("state")), params(scope, start, end, start, end));
    }

    private List<BreakdownEntry> workflowItems(String metric, double start, double end,
                                               List<String> owners) {
        OwnerScope scope = ownerScope(owners, "t.owner_id");
        String sql = """
                SELECT t.workflow_id, COALESCE(d.name, '') AS name, COUNT(*) AS total,
                 SUM(CASE WHEN t.state = 'done' THEN 1 ELSE 0 END) AS done,
                 SUM(CASE WHEN t.state = 'failed' THEN 1 ELSE 0 END) AS failed,
                 AVG(CASE WHEN t.state = 'done' THEN t.updated_at - t.created_at END) AS avg_done
                 FROM task_tasks t LEFT JOIN wf_defs d ON d.workflow_id = t.workflow_id
                 WHERE t.created_at BETWEEN ? AND ? AND t.workflow_id IS NOT NULL
                """ + scope.sql() + " GROUP BY t.workflow_id";
        return jdbc.query(sql, (row, index) -> {
            String workflowId = row.getString("workflow_id");
            String name = row.getString("name");
            int total = row.getInt("total");
            int done = row.getInt("done");
            int failed = row.getInt("failed");
            double minutes = round1(row.getDouble("avg_done") / 60.0);
            double rate = percentage(done, total);
            Number value = "workflow_completion_rate".equals(metric) ? rate : minutes;
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("total", total);
            extra.put("done", done);
            extra.put("failed", failed);
            extra.put("avg_minutes", minutes);
            return new BreakdownEntry(workflowId,
                    name == null || name.isEmpty() ? workflowId : name, value, extra);
        }, params(scope, start, end));
    }

    private List<BreakdownEntry> agentItems(String metric, double start, double end,
                                            List<String> owners) {
        OwnerScope scope = ownerScope(owners, "r.assigned_employee_id");
        String sql = """
                SELECT r.assigned_employee_id AS employee_id,
                 COALESCE(e.display_name, '') AS name, COUNT(*) AS total,
                 SUM(CASE WHEN r.state = 'failed' THEN 1 ELSE 0 END) AS failed,
                 SUM(CASE WHEN r.state IN ('dispatched','running','blocked') THEN 1 ELSE 0 END) AS active
                 FROM task_node_runs r
                 LEFT JOIN identity_employees e ON e.employee_id = r.assigned_employee_id
                 WHERE r.assigned_employee_id IS NOT NULL
                 AND COALESCE(r.started_at, r.dispatched_at, 0) BETWEEN ? AND ?
                """ + scope.sql() + " GROUP BY r.assigned_employee_id";
        return jdbc.query(sql, (row, index) -> {
            String employeeId = row.getString("employee_id");
            String name = row.getString("name");
            int total = row.getInt("total");
            int failed = row.getInt("failed");
            int active = row.getInt("active");
            Number value;
            if ("agent_load".equals(metric)) {
                value = total;
            } else {
                value = percentage(failed, total);
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("total", total);
            extra.put("failed", failed);
            extra.put("active", active);
            return new BreakdownEntry(employeeId,
                    name == null || name.isEmpty() ? employeeId : name, value, extra);
        }, params(scope, start, end));
    }

    private List<MetricDtos.MetricPointOut> cards(TaskSummary summary, int escalations,
                                                   int onlineAgents) {
        return List.of(
                new MetricDtos.MetricPointOut("tasks.total", summary.total(), "count", null),
                new MetricDtos.MetricPointOut("tasks.running", summary.active(), "count", null),
                new MetricDtos.MetricPointOut("tasks.completion_rate",
                        percentage(summary.done(), summary.total()), "percent", null),
                new MetricDtos.MetricPointOut("tasks.avg_done_minutes",
                        summary.avgDoneMinutes(), "minutes", null),
                new MetricDtos.MetricPointOut("tasks.failure_rate",
                        percentage(summary.failed(), summary.total()), "percent", null),
                new MetricDtos.MetricPointOut("tasks.escalations", escalations, "count", null),
                new MetricDtos.MetricPointOut("agents.online", onlineAgents, "count", null),
                new MetricDtos.MetricPointOut("tasks.backlog", summary.queued(), "count", null));
    }

    private List<Map<String, Object>> points(List<TimelineRow> timeline, String metric,
                                             double start, double end, int step) {
        Map<Integer, Integer> counts = new LinkedHashMap<>();
        for (TimelineRow row : timeline) {
            if ("tasks.created".equals(metric)
                    && start <= row.createdAt() && row.createdAt() <= end) {
                int index = (int) Math.floor((row.createdAt() - start) / step);
                counts.put(index, counts.getOrDefault(index, 0) + 1);
            }
            if ("tasks.completed".equals(metric) && "done".equals(row.state())
                    && start <= row.updatedAt() && row.updatedAt() <= end) {
                int index = (int) Math.floor((row.updatedAt() - start) / step);
                counts.put(index, counts.getOrDefault(index, 0) + 1);
            }
        }
        int buckets = Math.max(1, (int) ((end - start) / step) + 1);
        List<Map<String, Object>> result = new ArrayList<>();
        for (int index = 0; index < buckets; index++) {
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("ts", iso(start + (double) index * step));
            point.put("value", counts.getOrDefault(index, 0));
            result.add(point);
        }
        return result;
    }

    private int bucketSeconds(String bucket) {
        if (Set.of("1h", "hour").contains(bucket)) {
            return 3600;
        }
        if (Set.of("1d", "day").contains(bucket)) {
            return 86400;
        }
        throw unprocessable("不支持的 bucket：" + bucket);
    }

    private Range range(String from, String to) {
        Double parsedEnd = parseTime(to);
        double end = parsedEnd == null ? epochNow() : parsedEnd;
        Double parsedStart = parseTime(from);
        double start = parsedStart == null ? end - 7.0 * 86400.0 : parsedStart;
        if (start > end) {
            throw unprocessable("from 不能晚于 to");
        }
        return new Range(start, end);
    }

    private Double parseTime(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        String text = value.strip().replace("Z", "+00:00");
        String normalized = text.replace(' ', 'T');
        try {
            try {
                TemporalAccessor parsed = DateTimeFormatter.ISO_DATE_TIME.parseBest(
                        normalized, OffsetDateTime::from, LocalDateTime::from);
                if (parsed instanceof OffsetDateTime offset) {
                    return epoch(offset.toInstant());
                }
                return epoch(((LocalDateTime) parsed).toInstant(ZoneOffset.UTC));
            } catch (DateTimeParseException ignored) {
                return epoch(LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE)
                        .atStartOfDay().toInstant(ZoneOffset.UTC));
            }
        } catch (DateTimeException exception) {
            throw unprocessable("时间格式不合法：" + value);
        }
    }

    private double epochNow() {
        return epoch(Instant.now().truncatedTo(ChronoUnit.MICROS));
    }

    private double epoch(Instant instant) {
        return instant.getEpochSecond() + instant.getNano() / 1_000_000_000.0;
    }

    private String iso(double epoch) {
        long seconds = (long) Math.floor(epoch);
        long micros = Math.round((epoch - seconds) * 1_000_000.0);
        if (micros == 1_000_000) {
            seconds++;
            micros = 0;
        }
        String text = DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(
                LocalDateTime.ofEpochSecond(seconds, 0, ZoneOffset.UTC));
        if (micros != 0) {
            text += String.format(Locale.ROOT, ".%06d", micros);
        }
        return text + "+00:00";
    }

    private double percentage(int part, int total) {
        return total == 0 ? 0.0 : round1((double) part / total * 100.0);
    }

    private double round1(double value) {
        return BigDecimal.valueOf(value).setScale(1, RoundingMode.HALF_EVEN).doubleValue();
    }

    private OwnerScope ownerScope(List<String> owners, String column) {
        if (owners == null) {
            return new OwnerScope("", List.of());
        }
        if (owners.isEmpty()) {
            return new OwnerScope(" AND 1 = 0", List.of());
        }
        String marks = String.join(", ", java.util.Collections.nCopies(owners.size(), "?"));
        return new OwnerScope(" AND " + column + " IN (" + marks + ")", owners);
    }

    private Object[] params(OwnerScope scope, Object... leading) {
        Object[] result = new Object[leading.length + scope.params().size()];
        System.arraycopy(leading, 0, result, 0, leading.length);
        for (int index = 0; index < scope.params().size(); index++) {
            result[leading.length + index] = scope.params().get(index);
        }
        return result;
    }

    private void csvBreakdownRows(StringBuilder buffer, String section,
                                  MetricDtos.MetricBreakdownOut report) {
        for (MetricDtos.MetricBreakdownItemOut item : report.items()) {
            csvRow(buffer, section, item.key(), item.label(), report.metric(), item.value(), "count");
        }
    }

    private void csvRow(StringBuilder buffer, Object... values) {
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                buffer.append(',');
            }
            buffer.append(csvValue(values[index]));
        }
        buffer.append("\r\n");
    }

    private String csvValue(Object value) {
        if (value == null) {
            return "";
        }
        String text = String.valueOf(value);
        if (text.indexOf(',') >= 0 || text.indexOf('"') >= 0
                || text.indexOf('\r') >= 0 || text.indexOf('\n') >= 0) {
            return '"' + text.replace("\"", "\"\"") + '"';
        }
        return text;
    }

    private ApiException unprocessable(String message) {
        return ApiException.unprocessable("unprocessable", message);
    }

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

    private record TaskSummary(int total, int queued, int active, int done,
                               int failed, int cancelled, double avgDoneMinutes) {
    }

    private record TimelineRow(double createdAt, double updatedAt, String state) {
    }

    private record BreakdownEntry(String key, String label, Number value,
                                  Map<String, Object> extra) {
    }

    private record Range(double start, double end) {
    }

    private record OwnerScope(String sql, List<String> params) {
    }

    private record RuleRow(String ruleId, String metric, String op, double threshold,
                           String severity, boolean enabled, String note,
                           List<String> actions) {
    }
}
