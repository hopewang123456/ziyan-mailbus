package io.github.hopewang123456.mailbus.agents;

import java.time.Instant;
import java.util.List;

public record AgentInvite(
        String inviteId,
        String codeHash,
        String employeeName,
        String positionId,
        List<String> capabilities,
        List<String> permissions,
        String dataScope,
        String agentType,
        String channelType,
        Instant expiresAt,
        String createdBy,
        Instant createdAt,
        String usedByAgentId,
        Instant usedAt,
        Instant revokedAt,
        String revokedBy
) {
}
