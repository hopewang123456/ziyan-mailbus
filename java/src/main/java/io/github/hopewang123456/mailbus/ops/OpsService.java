package io.github.hopewang123456.mailbus.ops;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
public class OpsService {

    private static final Logger log = LoggerFactory.getLogger(OpsService.class);
    private static final int EXPORT_LIMIT = 5000;
    private static final int NOTIFY_ATTEMPTS = 3;
    private static final long BACKOFF_BASE_MILLIS = 500;

    private final OpsRepository repository;
    private final Ids ids;
    private final AlertNotifier notifier;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactions;

    public OpsService(OpsRepository repository, Ids ids, AlertNotifier notifier,
                      ObjectMapper objectMapper, PlatformTransactionManager transactionManager) {
        this.repository = repository;
        this.ids = ids;
        this.notifier = notifier;
        this.objectMapper = objectMapper;
        this.transactions = new TransactionTemplate(transactionManager);
    }

    // ---- 审计 ----

    public OpsModels.Page<OpsModels.AuditEntry> listAudit(
            Actor actor, String actorId, String action, String resource, Double start, Double end,
            int limit, int offset) {
        requireLog(actor);
        List<OpsModels.AuditEntry> rows = repository.listAudit(
                actorId, action, resource, start, end, limit, offset);
        int total = repository.countAudit(actorId, action, resource, start, end);
        return new OpsModels.Page<>(rows, total, limit, offset);
    }

    public OpsModels.AuditEntry getAudit(Actor actor, long auditId) {
        requireLog(actor);
        OpsModels.AuditEntry entry = repository.findAudit(auditId)
                .orElseThrow(() -> ApiException.notFound("审计记录不存在"));
        List<Map<String, Object>> diff = OpsRules.diffDetail(entry.detail());
        if (diff.isEmpty()) {
            return entry;
        }
        Map<String, Object> detail = new LinkedHashMap<>(entry.detail());
        detail.put("diff", diff);
        return new OpsModels.AuditEntry(entry.auditId(), entry.actorId(), entry.action(),
                entry.resource(), detail, entry.createdAt());
    }

    public String exportAuditCsv(Actor actor, String actorId, String action, String resource,
                                 Double start, Double end) {
        requireLog(actor);
        List<OpsModels.AuditEntry> rows = repository.listAudit(
                actorId, action, resource, start, end, EXPORT_LIMIT, 0);
        StringBuilder csv = new StringBuilder("\uFEFF");
        csvRow(csv, "audit_id", "created_at", "actor_id", "action", "resource", "detail");
        for (OpsModels.AuditEntry entry : rows) {
            csvRow(csv, String.valueOf(entry.auditId()),
                    entry.createdAt() == null ? "" : entry.createdAt().toString(),
                    entry.actorId(), entry.action(), entry.resource(), json(entry.detail()));
        }
        return csv.toString();
    }

    // ---- 告警 ----

    public OpsModels.Page<OpsModels.Alert> listAlerts(
            Actor actor, String state, String severity, int limit, int offset) {
        requireLog(actor);
        return new OpsModels.Page<>(repository.listAlerts(state, severity, limit, offset),
                repository.countAlerts(state, severity), limit, offset);
    }

    @Transactional
    public OpsModels.Alert ackAlert(Actor actor, String alertId) {
        requireLog(actor);
        OpsModels.Alert current = repository.findAlert(alertId)
                .orElseThrow(() -> ApiException.notFound("告警不存在"));
        OpsModels.Alert updated = OpsRules.ack(current, actor.employeeId(), Instant.now());
        repository.saveAlert(updated);
        repository.recordAudit(actor.employeeId(), "alert.acked", alertId, Map.of(), Instant.now());
        return updated;
    }

    // ---- 通知规则 ----

    public OpsModels.Page<OpsModels.AlertRule> listRules(Actor actor, int limit, int offset) {
        requireAdmin(actor);
        return new OpsModels.Page<>(repository.listRules(limit, offset), repository.countRules(),
                limit, offset);
    }

    @Transactional
    public OpsModels.AlertRule createRule(Actor actor, OpsModels.AlertRuleIn input) {
        requireAdmin(actor);
        validateName(input.name());
        String channel = input.channel() == null ? "inapp" : input.channel();
        int silenceSeconds = input.silenceSeconds() == null ? 300 : input.silenceSeconds();
        double threshold = OpsRules.normalizeRule(input.alertType(), channel, input.threshold(),
                silenceSeconds);
        Instant now = Instant.now();
        OpsModels.AlertRule rule = new OpsModels.AlertRule(ids.next("alr"), input.name().strip(),
                input.alertType(), threshold, channel, input.target(), silenceSeconds,
                input.enabled() == null || input.enabled(), actor.employeeId(), now);
        saveRule(actor, rule, "alert_rule.created", now);
        return rule;
    }

    @Transactional
    public OpsModels.AlertRule updateRule(Actor actor, String ruleId, Map<String, Object> changes) {
        requireAdmin(actor);
        OpsModels.AlertRule current = repository.findRule(ruleId)
                .orElseThrow(() -> ApiException.notFound("告警规则不存在"));
        String name = current.name();
        if (changes.get("name") != null) {
            name = string(changes.get("name"), "name");
            validateName(name);
            name = name.strip();
        }
        String alertType = changes.get("alert_type") == null ? current.alertType()
                : string(changes.get("alert_type"), "alert_type");
        String channel = changes.get("channel") == null ? current.channel()
                : string(changes.get("channel"), "channel");
        Double threshold = changes.get("threshold") == null ? current.threshold()
                : number(changes.get("threshold"), "threshold");
        int silenceSeconds = changes.get("silence_seconds") == null ? current.silenceSeconds()
                : integer(changes.get("silence_seconds"), "silence_seconds");
        String target = changes.containsKey("target")
                ? nullableString(changes.get("target"), "target") : current.target();
        boolean enabled = changes.get("enabled") == null ? current.enabled()
                : bool(changes.get("enabled"), "enabled");
        double normalized = OpsRules.normalizeRule(alertType, channel, threshold, silenceSeconds);
        OpsModels.AlertRule rule = new OpsModels.AlertRule(current.ruleId(), name, alertType,
                normalized, channel, target, silenceSeconds, enabled, current.createdBy(),
                current.createdAt());
        saveRule(actor, rule, "alert_rule.updated", Instant.now());
        return rule;
    }

    @Transactional
    public void deleteRule(Actor actor, String ruleId) {
        requireAdmin(actor);
        repository.findRule(ruleId).orElseThrow(() -> ApiException.notFound("告警规则不存在"));
        repository.deleteRule(ruleId);
        repository.recordAudit(actor.employeeId(), "alert_rule.deleted", ruleId, Map.of(),
                Instant.now());
    }

    public OpsModels.AlertRuleTestOut testRule(Actor actor, String ruleId) {
        requireAdmin(actor);
        OpsModels.AlertRule rule = repository.findRule(ruleId)
                .orElseThrow(() -> ApiException.notFound("告警规则不存在"));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("rule_id", rule.ruleId());
        payload.put("type", rule.alertType());
        payload.put("test", true);
        payload.put("at", Instant.now().toString());
        OpsModels.Delivery result = deliver(rule.channel(), rule.target(), payload);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("ok", result.ok());
        detail.put("attempts", result.attempts());
        detail.put("error", result.error());
        repository.recordAudit(actor.employeeId(), "alert_rule.tested", ruleId, detail,
                Instant.now());
        String message = result.ok() ? "测试通知已发送" : "测试通知发送失败：" + result.error();
        return new OpsModels.AlertRuleTestOut(ruleId, result.ok(), message);
    }

    // ---- 周期评估 ----

    public int evaluate() {
        return evaluate(Instant.now());
    }

    public int evaluate(Instant now) {
        int created = 0;
        for (OpsModels.AlertRule rule : repository.listEnabledRules()) {
            try {
                List<OpsModels.Alert> fresh = transactions.execute(status ->
                        evaluateRule(rule, now));
                if (fresh == null) {
                    continue;
                }
                for (OpsModels.Alert alert : fresh) {
                    notify(rule, alert, now);
                }
                created += fresh.size();
            } catch (Exception exception) {
                // 单条规则失败不阻断其它规则。
                log.warn("告警规则评估失败：{}", rule.ruleId(), exception);
            }
        }
        return created;
    }

    private List<OpsModels.Alert> evaluateRule(OpsModels.AlertRule rule, Instant now) {
        List<OpsModels.Breach> breaches = breaches(rule, now);
        Map<String, OpsModels.Alert> active = new LinkedHashMap<>();
        repository.activeAlerts(rule.ruleId()).forEach(alert -> active.put(alert.resourceId(), alert));
        List<OpsModels.Alert> fresh = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (OpsModels.Breach breach : breaches) {
            seen.add(breach.resourceId());
            OpsModels.Alert existing = active.get(breach.resourceId());
            OpsModels.Alert alert;
            if (existing == null) {
                alert = new OpsModels.Alert(ids.next("alert"), rule.ruleId(), rule.alertType(),
                        OpsRules.severityOf(rule.alertType()), breach.resourceType(),
                        breach.resourceId(), "firing", breach.value(), breach.threshold(), now, now,
                        null, null, null);
                fresh.add(alert);
            } else {
                alert = new OpsModels.Alert(existing.alertId(), existing.ruleId(), existing.type(),
                        existing.severity(), existing.resourceType(), existing.resourceId(),
                        existing.status(), breach.value(), breach.threshold(), existing.firstSeenAt(),
                        now, existing.ackedBy(), existing.ackedAt(), existing.resolvedAt());
            }
            repository.saveAlert(alert);
        }
        for (Map.Entry<String, OpsModels.Alert> item : active.entrySet()) {
            if (!seen.contains(item.getKey())) {
                OpsModels.Alert existing = item.getValue();
                repository.saveAlert(new OpsModels.Alert(existing.alertId(), existing.ruleId(),
                        existing.type(), existing.severity(), existing.resourceType(),
                        existing.resourceId(), "resolved", existing.value(), existing.threshold(),
                        existing.firstSeenAt(), now, existing.ackedBy(), existing.ackedAt(), now));
            }
        }
        return fresh;
    }

    private void notify(OpsModels.AlertRule rule, OpsModels.Alert alert, Instant now) {
        String resource = rule.ruleId() + ":" + alert.resourceType() + ":" + alert.resourceId();
        Instant last = repository.lastNotification(resource);
        if (!OpsRules.shouldNotify(last, now, rule.silenceSeconds())) {
            return;
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("alert_id", alert.alertId());
        payload.put("rule_id", rule.ruleId());
        payload.put("type", alert.type());
        payload.put("severity", alert.severity());
        payload.put("resource_type", alert.resourceType());
        payload.put("resource_id", alert.resourceId());
        payload.put("value", alert.value());
        payload.put("threshold", alert.threshold());
        payload.put("at", now.toString());
        OpsModels.Delivery result = deliver(rule.channel(), rule.target(), payload);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("alert_id", alert.alertId());
        detail.put("channel", rule.channel());
        detail.put("target", rule.target());
        detail.put("ok", result.ok());
        detail.put("attempts", result.attempts());
        detail.put("error", result.error());
        repository.recordAudit(null, "alert.notified", resource, detail, Instant.now());
    }

    private OpsModels.Delivery deliver(String channel, String target, Map<String, Object> payload) {
        String error = null;
        for (int attempt = 1; attempt <= NOTIFY_ATTEMPTS; attempt++) {
            try {
                notifier.send(channel, target, payload);
                return new OpsModels.Delivery(true, attempt, null);
            } catch (Exception exception) {
                error = exception.getMessage() == null || exception.getMessage().isEmpty()
                        ? exception.getClass().getSimpleName() : exception.getMessage();
                if (attempt < NOTIFY_ATTEMPTS) {
                    try {
                        Thread.sleep(BACKOFF_BASE_MILLIS * (1L << (attempt - 1)));
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return new OpsModels.Delivery(false, attempt, error);
                    }
                }
            }
        }
        return new OpsModels.Delivery(false, NOTIFY_ATTEMPTS, error);
    }

    private List<OpsModels.Breach> breaches(OpsModels.AlertRule rule, Instant now) {
        double threshold = rule.threshold() == null ? 0.0 : rule.threshold();
        switch (rule.alertType()) {
            case OpsRules.OUTBOX_BACKLOG -> {
                int count = repository.outboxBacklog();
                return count > threshold
                        ? List.of(new OpsModels.Breach("outbox", "outbox", String.valueOf(count),
                        general(threshold))) : List.of();
            }
            case OpsRules.WORKFLOW_FAILURE_RATE -> {
                return failureBreaches(threshold, epoch(now) - 3600.0);
            }
            case OpsRules.AGENT_OFFLINE -> {
                return timedBreaches("agent", repository.offlineAgents(epoch(now) - threshold),
                        now, threshold);
            }
            case OpsRules.RUN_TIMEOUT -> {
                return timedBreaches("run", repository.timedOutRuns(epoch(now) - threshold),
                        now, threshold);
            }
            default -> {
                return timedBreaches("escalation",
                        repository.staleEscalations(epoch(now) - threshold), now, threshold);
            }
        }
    }

    private List<OpsModels.Breach> failureBreaches(double threshold, double since) {
        List<OpsModels.Breach> result = new ArrayList<>();
        for (OpsModels.WorkflowFailure workflow : repository.workflowFailures(since)) {
            if (workflow.total() <= 0) {
                continue;
            }
            double rate = (double) workflow.failed() / workflow.total() * 100.0;
            if (rate > threshold) {
                result.add(new OpsModels.Breach("workflow", workflow.workflowId(),
                        String.format(Locale.ROOT, "%.1f%%", rate), general(threshold) + "%"));
            }
        }
        return result;
    }

    private List<OpsModels.Breach> timedBreaches(
            String type, List<OpsModels.TimestampedResource> resources, Instant now, double threshold) {
        List<OpsModels.Breach> result = new ArrayList<>();
        for (OpsModels.TimestampedResource resource : resources) {
            String value = String.format(Locale.ROOT, "%.1fmin",
                    (epoch(now) - resource.timestamp()) / 60.0);
            result.add(new OpsModels.Breach(type, resource.resourceId(), value,
                    general(threshold) + "s"));
        }
        return result;
    }

    private void saveRule(Actor actor, OpsModels.AlertRule rule, String action, Instant now) {
        repository.saveRule(rule);
        repository.recordAudit(actor.employeeId(), action, rule.ruleId(),
                Map.of("alert_type", rule.alertType(), "enabled", rule.enabled()), now);
    }

    private static void requireLog(Actor actor) {
        Authz.ensureAnyAllowed(actor, Set.of(Authz.LOG_READ, Authz.CONSOLE_ADMIN),
                Authz.Resource.of("audit"));
    }

    private static void requireAdmin(Actor actor) {
        Authz.ensureAnyAllowed(actor, Set.of(Authz.CONSOLE_ADMIN, Authz.SYSTEM_CONFIG),
                Authz.Resource.of("alert_rule"));
    }

    public static Double parseTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String text = value.strip();
        if (text.length() > 10 && text.charAt(10) == ' ') {
            text = text.substring(0, 10) + "T" + text.substring(11);
        }
        try {
            try {
                return epoch(OffsetDateTime.parse(text, DateTimeFormatter.ISO_OFFSET_DATE_TIME)
                        .toInstant());
            } catch (DateTimeParseException ignored) {
                try {
                    return epoch(LocalDateTime.parse(text, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                            .toInstant(ZoneOffset.UTC));
                } catch (DateTimeParseException ignoredLocal) {
                    return (double) LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE)
                            .atStartOfDay().toEpochSecond(ZoneOffset.UTC);
                }
            }
        } catch (DateTimeParseException exception) {
            throw ApiException.unprocessable();
        }
    }

    private static void validateName(String name) {
        if (name == null || name.isEmpty() || name.length() > 64) {
            throw ApiException.unprocessable();
        }
    }

    private static String string(Object value, String field) {
        if (!(value instanceof String text)) {
            throw ApiException.unprocessable();
        }
        return text;
    }

    private static String nullableString(Object value, String field) {
        return value == null ? null : string(value, field);
    }

    private static Double number(Object value, String field) {
        if (!(value instanceof Number number)) {
            throw ApiException.unprocessable();
        }
        return number.doubleValue();
    }

    private static int integer(Object value, String field) {
        if (!(value instanceof Number number)) {
            throw ApiException.unprocessable();
        }
        double candidate = number.doubleValue();
        if (candidate != Math.rint(candidate) || candidate < 0 || candidate > Integer.MAX_VALUE) {
            throw ApiException.unprocessable();
        }
        return (int) candidate;
    }

    private static boolean bool(Object value, String field) {
        if (!(value instanceof Boolean enabled)) {
            throw ApiException.unprocessable();
        }
        return enabled;
    }

    private static String general(double value) {
        String formatted = String.format(Locale.ROOT, "%.6g", value);
        int exponent = formatted.indexOf('e');
        String suffix = "";
        if (exponent >= 0) {
            suffix = formatted.substring(exponent);
            formatted = formatted.substring(0, exponent);
        }
        if (formatted.contains(".")) {
            int end = formatted.length();
            while (end > 0 && formatted.charAt(end - 1) == '0') {
                end--;
            }
            if (end > 0 && formatted.charAt(end - 1) == '.') {
                end--;
            }
            formatted = formatted.substring(0, end);
        }
        return formatted + suffix;
    }

    private static double epoch(Instant value) {
        return value.getEpochSecond() + value.getNano() / 1_000_000_000.0;
    }

    private static void csvRow(StringBuilder csv, String... values) {
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                csv.append(',');
            }
            csvField(csv, values[index] == null ? "" : values[index]);
        }
        csv.append("\r\n");
    }

    private static void csvField(StringBuilder csv, String value) {
        if (value.indexOf(',') >= 0 || value.indexOf('"') >= 0
                || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            csv.append('"').append(value.replace("\"", "\"\"")).append('"');
        } else {
            csv.append(value);
        }
    }

    private String json(Map<String, Object> detail) {
        try {
            return objectMapper.writeValueAsString(detail);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("审计详情序列化失败", exception);
        }
    }
}
