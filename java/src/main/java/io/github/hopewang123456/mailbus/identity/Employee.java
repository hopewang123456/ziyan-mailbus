package io.github.hopewang123456.mailbus.identity;

import java.time.Instant;
import java.util.List;
import java.util.Set;

public record Employee(
        String employeeId,
        String displayName,
        String accountType,
        String status,
        String teamId,
        String positionId,
        String seatId,
        String agentId,
        Set<String> capabilities,
        String dataScope,
        List<String> fileScope,
        String endpoint,
        boolean endpointApproved,
        Instant approvedAt,
        Instant lastHeartbeat
) {
}
