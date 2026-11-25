package io.github.hopewang123456.mailbus.agents;

import java.time.Instant;

public record Agent(
        String agentId,
        String name,
        String framework,
        String model,
        String endpoint,
        boolean enabled,
        Instant createdAt,
        Instant updatedAt,
        String agentType,
        String channelType,
        String endpointToken,
        String endpointTokenLookupHash,
        String endpointTokenPrev,
        String endpointTokenPrevLookupHash,
        Instant endpointTokenPrevExpiresAt,
        Instant lastSeenAt,
        String pendingEndpoint,
        String endpointReviewStatus,
        String endpointApprovedBy,
        Instant endpointApprovedAt,
        Instant deletedAt,
        String deletedBy
) {
    /** 旧登记路径的兼容构造：新字段取安全默认值。 */
    public Agent(String agentId, String name, String framework, String model,
                 String endpoint, boolean enabled, Instant createdAt, Instant updatedAt) {
        this(agentId, name, framework, model, endpoint, enabled, createdAt, updatedAt,
                "service", "a2a", null, null, null, null, null, null, null,
                "pending", null, null, null, null);
    }
}
