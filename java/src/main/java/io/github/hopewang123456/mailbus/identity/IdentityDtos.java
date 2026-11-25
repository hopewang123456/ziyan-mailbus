package io.github.hopewang123456.mailbus.identity;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

public final class IdentityDtos {

    private IdentityDtos() {
    }

    public record SuperAdminIn(@NotBlank @Size(max = 64) String displayName, String employeeId) {
    }

    public record ModelConfigIn(@NotBlank @Size(max = 64) String provider,
                                @NotBlank @Size(max = 128) String model,
                                String apiBase) {
    }

    public record SessionOut(EmployeeView employee, String token) {
    }

    public record EmployeeView(
            String employeeId,
            String displayName,
            String accountType,
            String status,
            String teamId,
            String positionId,
            String seatId,
            String agentId,
            String agentName,
            String agentFramework,
            List<String> permissions,
            String dataScope,
            List<String> fileScope,
            String endpoint,
            boolean endpointApproved,
            Instant lastHeartbeat
    ) {
    }

    public record BootstrapStep(String step, boolean done, boolean skippable) {
    }

    public record BootstrapStatusOut(boolean completed, List<BootstrapStep> steps) {
    }

    public record LogoutIn() {
    }
}
