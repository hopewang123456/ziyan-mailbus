package io.github.hopewang123456.mailbus.ops;

import io.github.hopewang123456.mailbus.common.ApiException;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public final class OpsRules {

    public static final String AGENT_OFFLINE = "agent_offline";
    public static final String RUN_TIMEOUT = "run_timeout";
    public static final String ESCALATION_PENDING = "escalation_pending";
    public static final String OUTBOX_BACKLOG = "outbox_backlog";
    public static final String WORKFLOW_FAILURE_RATE = "workflow_failure_rate";

    private static final Set<String> ALERT_TYPES = Set.of(AGENT_OFFLINE, RUN_TIMEOUT,
            ESCALATION_PENDING, OUTBOX_BACKLOG, WORKFLOW_FAILURE_RATE);
    private static final Set<String> CHANNELS = Set.of("webhook", "email", "inapp");
    private static final Map<String, Double> DEFAULT_THRESHOLDS = Map.of(
            AGENT_OFFLINE, 300.0,
            RUN_TIMEOUT, 3600.0,
            ESCALATION_PENDING, 3600.0,
            OUTBOX_BACKLOG, 100.0,
            WORKFLOW_FAILURE_RATE, 20.0);
    private static final Map<String, String> SEVERITIES = Map.of(
            AGENT_OFFLINE, "warn",
            RUN_TIMEOUT, "warn",
            ESCALATION_PENDING, "info",
            OUTBOX_BACKLOG, "warn",
            WORKFLOW_FAILURE_RATE, "critical");

    private OpsRules() {
    }

    public static double normalizeRule(String alertType, String channel, Double threshold,
                                       int silenceSeconds) {
        if (alertType == null || !ALERT_TYPES.contains(alertType)) {
            throw ApiException.unprocessable("unprocessable", "不支持的告警类型：" + alertType);
        }
        if (channel == null || !CHANNELS.contains(channel)) {
            throw ApiException.unprocessable("unprocessable", "不支持的通知渠道：" + channel);
        }
        if (silenceSeconds < 0) {
            throw ApiException.unprocessable("unprocessable", "silence_seconds 不能为负数");
        }
        double value = threshold == null ? DEFAULT_THRESHOLDS.get(alertType) : threshold;
        if (value < 0) {
            throw ApiException.unprocessable("unprocessable", "阈值不能为负数");
        }
        return value;
    }

    public static String severityOf(String alertType) {
        return SEVERITIES.getOrDefault(alertType, "warn");
    }

    public static OpsModels.Alert ack(OpsModels.Alert alert, String actorId, Instant now) {
        if ("resolved".equals(alert.status())) {
            throw ApiException.invalid("告警已恢复，无需确认");
        }
        if ("acked".equals(alert.status())) {
            return alert;
        }
        return new OpsModels.Alert(alert.alertId(), alert.ruleId(), alert.type(), alert.severity(),
                alert.resourceType(), alert.resourceId(), "acked", alert.value(), alert.threshold(),
                alert.firstSeenAt(), alert.lastSeenAt(), actorId, now, alert.resolvedAt());
    }

    public static boolean shouldNotify(Instant lastSent, Instant now, int silenceSeconds) {
        return lastSent == null || !now.isBefore(lastSent.plusSeconds(silenceSeconds));
    }

    public static List<Map<String, Object>> diffDetail(Map<String, Object> detail) {
        Object beforeValue = detail.get("before");
        Object afterValue = detail.get("after");
        if (!(beforeValue instanceof Map<?, ?> before) || !(afterValue instanceof Map<?, ?> after)) {
            return List.of();
        }
        Set<String> keys = new TreeSet<>();
        before.keySet().forEach(key -> keys.add(String.valueOf(key)));
        after.keySet().forEach(key -> keys.add(String.valueOf(key)));
        List<Map<String, Object>> changes = new ArrayList<>();
        for (String key : keys) {
            Object oldValue = before.get(key);
            Object newValue = after.get(key);
            if (!jsonEquals(oldValue, newValue)) {
                Map<String, Object> change = new LinkedHashMap<>();
                change.put("field", key);
                change.put("before", oldValue);
                change.put("after", newValue);
                changes.add(change);
            }
        }
        return changes;
    }

    private static boolean jsonEquals(Object left, Object right) {
        if (left instanceof Number first && right instanceof Number second) {
            return new BigDecimal(first.toString()).compareTo(new BigDecimal(second.toString())) == 0;
        }
        if (left instanceof Map<?, ?> first && right instanceof Map<?, ?> second) {
            if (!first.keySet().equals(second.keySet())) {
                return false;
            }
            return first.keySet().stream().allMatch(key ->
                    jsonEquals(first.get(key), second.get(key)));
        }
        if (left instanceof List<?> first && right instanceof List<?> second) {
            if (first.size() != second.size()) {
                return false;
            }
            for (int index = 0; index < first.size(); index++) {
                if (!jsonEquals(first.get(index), second.get(index))) {
                    return false;
                }
            }
            return true;
        }
        return Objects.equals(left, right);
    }
}
