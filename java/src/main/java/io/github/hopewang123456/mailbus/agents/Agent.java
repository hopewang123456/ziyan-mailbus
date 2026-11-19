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
        Instant updatedAt
) {
}
