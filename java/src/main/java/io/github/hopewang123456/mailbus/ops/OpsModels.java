package io.github.hopewang123456.mailbus.ops;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class OpsModels {

    private OpsModels() {
    }

    public record AuditEntry(long auditId, String actorId, String action, String resource,
                             Map<String, Object> detail, Instant createdAt) {
    }

    public record AlertRule(String ruleId, String name, String alertType, Double threshold,
                            String channel, String target, int silenceSeconds, boolean enabled,
                            String createdBy, Instant createdAt) {
    }

    public record Alert(String alertId, String ruleId, String type, String severity,
                        String resourceType, String resourceId, String status, String value,
                        String threshold, Instant firstSeenAt, Instant lastSeenAt,
                        String ackedBy, Instant ackedAt, Instant resolvedAt) {
    }

    public record Breach(String resourceType, String resourceId, String value, String threshold) {
    }

    public record AlertRuleIn(@NotNull @Size(min = 1, max = 64) String name,
                              @NotNull @Size(min = 1, max = 64) String alertType,
                              Double threshold, String channel, String target,
                              @Min(0) Integer silenceSeconds, Boolean enabled) {
    }

    public record AlertRuleTestOut(String ruleId, boolean ok, String messageZh) {
    }

    public record Page<T>(List<T> items, int total, int limit, int offset) {
    }

    public record TimestampedResource(String resourceId, double timestamp) {
    }

    public record WorkflowFailure(String workflowId, int total, int failed) {
    }

    record Delivery(boolean ok, int attempts, String error) {
    }
}
