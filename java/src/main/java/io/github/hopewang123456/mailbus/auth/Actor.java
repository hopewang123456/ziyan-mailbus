package io.github.hopewang123456.mailbus.auth;

import java.util.Set;

public record Actor(
        String employeeId,
        String displayName,
        String accountType,
        String status,
        String teamId,
        String dataScope,
        String fileScope,
        boolean endpointApproved,
        Set<String> capabilities
) {
    public boolean has(String capability) {
        return capabilities.contains("*") || capabilities.contains(capability);
    }
}
