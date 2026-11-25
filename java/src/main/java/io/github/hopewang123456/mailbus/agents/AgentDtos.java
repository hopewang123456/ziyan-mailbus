package io.github.hopewang123456.mailbus.agents;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class AgentDtos {

    private AgentDtos() {
    }

    public record AgentIn(@NotBlank @Size(max = 64) String name,
                          @Size(max = 64) String framework, String model,
                          String endpoint, Boolean enabled) {
    }

    public record AgentOut(String agentId, String name, String framework, String model,
                           String endpoint, String pendingEndpoint, String endpointReviewStatus,
                           boolean enabled, String agentType, String channelType, boolean online,
                           Instant lastSeenAt, Instant createdAt, Instant updatedAt) {

        public static AgentOut of(Agent agent, boolean online) {
            return new AgentOut(agent.agentId(), agent.name(), agent.framework(),
                    agent.model(), agent.endpoint(), agent.pendingEndpoint(),
                    agent.endpointReviewStatus(), agent.enabled(), agent.agentType(),
                    agent.channelType(), online, agent.lastSeenAt(), agent.createdAt(),
                    agent.updatedAt());
        }
    }

    public record AgentListOut(List<AgentOut> items, int total, int limit, int offset) {
    }

    public record AgentTokenOut(String agentId, String token, String fingerprint,
                                Instant expiresAt) {
    }

    public record AgentHealthOut(String agentId, boolean online, boolean endpointOk,
                                 Instant lastSeenAt) {
    }

    public record AgentRegisterIn(@NotBlank @Size(max = 128) String inviteCode,
                                  @NotBlank @Size(max = 64) String name,
                                  @Size(max = 64) String framework, String model,
                                  String endpoint, String agentType, String channelType) {
    }

    public record AgentRegisterOut(String agentId, String employeeId, String token,
                                   String endpoint, String endpointReviewStatus) {
    }

    public record AgentInviteIn(String employeeName, String positionId,
                                List<String> capabilities, List<String> permissions,
                                String dataScope, String agentType, String channelType,
                                Integer expiresInHours) {
    }

    public record AgentInviteOut(String inviteId, String inviteCode, String employeeName,
                                 String positionId, List<String> capabilities,
                                 List<String> permissions, String dataScope,
                                 String agentType, String channelType, String createdBy,
                                 Instant createdAt, Instant expiresAt,
                                 String usedByAgentId, Instant usedAt, Instant revokedAt) {
    }

    public record AgentInviteListOut(List<AgentInviteOut> items, int total, int limit,
                                     int offset) {
    }

    public record A2aArtifactIn(String type, String filePath, String artifactId,
                                String fileName, String description) {
    }

    public record A2aMessageIn(String type, String messageId, String runId, Integer attemptNo,
                               String status, String output, List<A2aArtifactIn> artifacts,
                               String endpoint, Integer pendingTasks, Instant completedAt,
                               String body, Map<String, Object> payload) {
    }

    public record A2aAckOut(String messageId, boolean accepted, boolean duplicate) {
    }

    public record AgentPatch(Map<String, Object> fields) {
    }
}
