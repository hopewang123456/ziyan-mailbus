package io.github.hopewang123456.mailbus.ops;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Repository
public class OpsRepository {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public OpsRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    // ---- 审计 ----

    public List<OpsModels.AuditEntry> listAudit(String actor, String action, String resource,
                                                Double start, Double end, int limit, int offset) {
        List<Object> params = new ArrayList<>();
        String where = auditFilters(actor, action, resource, start, end, params);
        params.add(limit);
        params.add(offset);
        return jdbc.query("SELECT * FROM ops_audit_log" + where
                        + " ORDER BY created_at DESC, audit_id DESC LIMIT ? OFFSET ?",
                this::mapAudit, params.toArray());
    }

    public int countAudit(String actor, String action, String resource, Double start, Double end) {
        List<Object> params = new ArrayList<>();
        String where = auditFilters(actor, action, resource, start, end, params);
        Integer total = jdbc.queryForObject("SELECT COUNT(*) FROM ops_audit_log" + where,
                Integer.class, params.toArray());
        return total == null ? 0 : total;
    }

    public Optional<OpsModels.AuditEntry> findAudit(long auditId) {
        return jdbc.query("SELECT * FROM ops_audit_log WHERE audit_id = ?", this::mapAudit, auditId)
                .stream().findFirst();
    }

    public void recordAudit(String actorId, String action, String resource,
                            Map<String, Object> detail, Instant now) {
        jdbc.update("INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)"
                        + " VALUES (?, ?, ?, ?, ?)", actorId, action, resource, json(detail),
                epoch(now));
    }

    // ---- 通知规则 ----

    public List<OpsModels.AlertRule> listRules(int limit, int offset) {
        return jdbc.query("SELECT * FROM ops_alert_rules ORDER BY created_at DESC, rule_id"
                + " LIMIT ? OFFSET ?", this::mapRule, limit, offset);
    }

    public int countRules() {
        Integer total = jdbc.queryForObject("SELECT COUNT(*) FROM ops_alert_rules", Integer.class);
        return total == null ? 0 : total;
    }

    public List<OpsModels.AlertRule> listEnabledRules() {
        return jdbc.query("SELECT * FROM ops_alert_rules WHERE enabled = 1 ORDER BY rule_id",
                this::mapRule);
    }

    public Optional<OpsModels.AlertRule> findRule(String ruleId) {
        return jdbc.query("SELECT * FROM ops_alert_rules WHERE rule_id = ?", this::mapRule, ruleId)
                .stream().findFirst();
    }

    public void saveRule(OpsModels.AlertRule rule) {
        jdbc.update("""
                INSERT INTO ops_alert_rules
                    (rule_id, name, alert_type, threshold, channel, target, silence_seconds,
                     enabled, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (rule_id) DO UPDATE SET
                    name = excluded.name, alert_type = excluded.alert_type,
                    threshold = excluded.threshold, channel = excluded.channel,
                    target = excluded.target, silence_seconds = excluded.silence_seconds,
                    enabled = excluded.enabled
                """, rule.ruleId(), rule.name(), rule.alertType(), rule.threshold(), rule.channel(),
                rule.target(), rule.silenceSeconds(), rule.enabled() ? 1 : 0, rule.createdBy(),
                epoch(rule.createdAt()));
    }

    public void deleteRule(String ruleId) {
        jdbc.update("DELETE FROM ops_alert_rules WHERE rule_id = ?", ruleId);
    }

    // ---- 告警 ----

    public List<OpsModels.Alert> listAlerts(String state, String severity, int limit, int offset) {
        List<Object> params = new ArrayList<>();
        String where = alertFilters(state, severity, params);
        params.add(limit);
        params.add(offset);
        return jdbc.query("SELECT * FROM ops_alerts" + where
                        + " ORDER BY last_seen_at DESC, alert_id LIMIT ? OFFSET ?",
                this::mapAlert, params.toArray());
    }

    public int countAlerts(String state, String severity) {
        List<Object> params = new ArrayList<>();
        String where = alertFilters(state, severity, params);
        Integer total = jdbc.queryForObject("SELECT COUNT(*) FROM ops_alerts" + where,
                Integer.class, params.toArray());
        return total == null ? 0 : total;
    }

    public Optional<OpsModels.Alert> findAlert(String alertId) {
        return jdbc.query("SELECT * FROM ops_alerts WHERE alert_id = ?", this::mapAlert, alertId)
                .stream().findFirst();
    }

    public void saveAlert(OpsModels.Alert alert) {
        jdbc.update("""
                INSERT INTO ops_alerts
                    (alert_id, rule_id, type, severity, resource_type, resource_id, status,
                     value, threshold, first_seen_at, last_seen_at, acked_by, acked_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (alert_id) DO UPDATE SET
                    status = excluded.status, value = excluded.value, threshold = excluded.threshold,
                    last_seen_at = excluded.last_seen_at, acked_by = excluded.acked_by,
                    acked_at = excluded.acked_at, resolved_at = excluded.resolved_at
                """, alert.alertId(), alert.ruleId(), alert.type(), alert.severity(),
                alert.resourceType(), alert.resourceId(), alert.status(), alert.value(),
                alert.threshold(), epoch(alert.firstSeenAt()), epoch(alert.lastSeenAt()),
                alert.ackedBy(), epoch(alert.ackedAt()), epoch(alert.resolvedAt()));
    }

    public List<OpsModels.Alert> activeAlerts(String ruleId) {
        return jdbc.query("SELECT * FROM ops_alerts WHERE rule_id = ? AND status != 'resolved'",
                this::mapAlert, ruleId);
    }

    // ---- 通知冷却与评估数据 ----

    public Instant lastNotification(String resource) {
        return jdbc.queryForObject("SELECT MAX(created_at) AS latest FROM ops_audit_log"
                + " WHERE action = 'alert.notified' AND resource = ?", (row, index) -> {
            double value = row.getDouble("latest");
            return row.wasNull() ? null : instant(value);
        }, resource);
    }

    public List<OpsModels.TimestampedResource> offlineAgents(double cutoff) {
        return jdbc.query("SELECT agent_id, last_seen_at FROM agents"
                        + " WHERE enabled = 1 AND deleted_at IS NULL"
                        + " AND last_seen_at IS NOT NULL AND last_seen_at < ? ORDER BY agent_id",
                (row, index) -> new OpsModels.TimestampedResource(row.getString("agent_id"),
                        row.getDouble("last_seen_at")), cutoff);
    }

    public List<OpsModels.TimestampedResource> timedOutRuns(double cutoff) {
        return jdbc.query("SELECT run_id, started_at FROM task_node_runs"
                        + " WHERE state = 'running' AND started_at IS NOT NULL AND started_at < ?"
                        + " ORDER BY run_id",
                (row, index) -> new OpsModels.TimestampedResource(row.getString("run_id"),
                        row.getDouble("started_at")), cutoff);
    }

    public List<OpsModels.TimestampedResource> staleEscalations(double cutoff) {
        return jdbc.query("SELECT e.escalation_id, r.started_at AS since FROM task_escalations e"
                        + " JOIN task_node_runs r ON r.run_id = e.run_id"
                        + " WHERE r.state = 'blocked' AND r.started_at IS NOT NULL"
                        + " AND r.started_at < ? ORDER BY e.escalation_id",
                (row, index) -> new OpsModels.TimestampedResource(row.getString("escalation_id"),
                        row.getDouble("since")), cutoff);
    }

    public int outboxBacklog() {
        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ops_outbox WHERE dispatched_at IS NULL", Integer.class);
        return total == null ? 0 : total;
    }

    public List<OpsModels.WorkflowFailure> workflowFailures(double since) {
        return jdbc.query("SELECT t.workflow_id, COUNT(*) AS total,"
                        + " SUM(CASE WHEN t.state = 'failed' THEN 1 ELSE 0 END) AS failed"
                        + " FROM task_tasks t WHERE t.created_at >= ? AND t.workflow_id IS NOT NULL"
                        + " GROUP BY t.workflow_id ORDER BY t.workflow_id",
                (row, index) -> new OpsModels.WorkflowFailure(row.getString("workflow_id"),
                        row.getInt("total"), row.getInt("failed")), since);
    }

    private OpsModels.AuditEntry mapAudit(ResultSet row, int index) throws SQLException {
        double createdAt = row.getDouble("created_at");
        boolean createdAtNull = row.wasNull();
        return new OpsModels.AuditEntry(row.getLong("audit_id"), row.getString("actor_id"),
                row.getString("action"), row.getString("resource"), detail(row.getString("detail")),
                createdAtNull ? null : instant(createdAt));
    }

    private OpsModels.AlertRule mapRule(ResultSet row, int index) throws SQLException {
        double threshold = row.getDouble("threshold");
        boolean thresholdNull = row.wasNull();
        return new OpsModels.AlertRule(row.getString("rule_id"), row.getString("name"),
                row.getString("alert_type"), thresholdNull ? null : threshold,
                row.getString("channel"), row.getString("target"), row.getInt("silence_seconds"),
                row.getInt("enabled") == 1, row.getString("created_by"),
                instant(row.getDouble("created_at")));
    }

    private OpsModels.Alert mapAlert(ResultSet row, int index) throws SQLException {
        return new OpsModels.Alert(row.getString("alert_id"), row.getString("rule_id"),
                row.getString("type"), row.getString("severity"), row.getString("resource_type"),
                row.getString("resource_id"), row.getString("status"), row.getString("value"),
                row.getString("threshold"), instant(row.getDouble("first_seen_at")),
                instant(row.getDouble("last_seen_at")), row.getString("acked_by"),
                nullableInstant(row, "acked_at"), nullableInstant(row, "resolved_at"));
    }

    private String auditFilters(String actor, String action, String resource, Double start,
                                Double end, List<Object> params) {
        List<String> clauses = new ArrayList<>();
        if (actor != null && !actor.isEmpty()) {
            clauses.add("actor_id = ?");
            params.add(actor);
        }
        if (action != null && !action.isEmpty()) {
            clauses.add("action = ?");
            params.add(action);
        }
        if (resource != null && !resource.isEmpty()) {
            clauses.add("resource = ?");
            params.add(resource);
        }
        if (start != null) {
            clauses.add("created_at >= ?");
            params.add(start);
        }
        if (end != null) {
            clauses.add("created_at <= ?");
            params.add(end);
        }
        return clauses.isEmpty() ? "" : " WHERE " + String.join(" AND ", clauses);
    }

    private String alertFilters(String state, String severity, List<Object> params) {
        List<String> clauses = new ArrayList<>();
        if (state != null && !state.isEmpty()) {
            clauses.add("status = ?");
            params.add(state);
        }
        if (severity != null && !severity.isEmpty()) {
            clauses.add("severity = ?");
            params.add(severity);
        }
        return clauses.isEmpty() ? "" : " WHERE " + String.join(" AND ", clauses);
    }

    private Map<String, Object> detail(String value) {
        try {
            return objectMapper.readValue(value == null || value.isBlank() ? "{}" : value,
                    new TypeReference<>() {
                    });
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("审计详情解析失败", exception);
        }
    }

    private String json(Map<String, Object> detail) {
        try {
            return objectMapper.writeValueAsString(detail);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("审计详情序列化失败", exception);
        }
    }

    private static Instant nullableInstant(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : instant(value);
    }

    private static Instant instant(double value) {
        BigDecimal[] parts = BigDecimal.valueOf(value).divideAndRemainder(BigDecimal.ONE);
        return Instant.ofEpochSecond(parts[0].longValue(),
                parts[1].movePointRight(9).longValue());
    }

    private static Double epoch(Instant value) {
        return value == null ? null : value.getEpochSecond() + value.getNano() / 1_000_000_000.0;
    }
}
