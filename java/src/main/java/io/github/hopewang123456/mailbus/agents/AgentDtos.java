package io.github.hopewang123456.mailbus.agents;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.Map;

public final class AgentDtos {

    private AgentDtos() {
    }

    public record AgentIn(@NotBlank @Size(max = 64) String name,
                          @Size(max = 64) String framework, String model,
                          String endpoint, Boolean enabled) {
    }

    public record AgentOut(String agentId, String name, String framework, String model,
                           String endpoint, boolean enabled, Instant createdAt,
                           Instant updatedAt) {
        public static AgentOut of(Agent agent) {
            return new AgentOut(agent.agentId(), agent.name(), agent.framework(),
                    agent.model(), agent.endpoint(), agent.enabled(),
                    agent.createdAt(), agent.updatedAt());
        }
    }

    public record AgentPatch(Map<String, Object> fields) {
    }
}
