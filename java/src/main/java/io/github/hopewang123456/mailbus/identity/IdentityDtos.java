package io.github.hopewang123456.mailbus.identity;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

public final class IdentityDtos {

    private IdentityDtos() {
    }

    public record ApplyIn(
            @NotBlank @Size(max = 64) String displayName,
            @NotBlank @Pattern(regexp = "human|agent") String accountType,
            String inviteCode,
            String endpoint,
            String seatId,
            String agentId
    ) {
    }

    public record ApplyOut(EmployeeView employee, String token) {
    }

    public record ReviewIn(@NotNull Boolean approved, String note) {
    }

    public record InviteIn(
            @NotBlank @Pattern(regexp = "human|agent") String accountType,
            String teamId,
            String positionId,
            List<@Pattern(regexp = "message_send|message_read|task_create|task_dispatch"
                    + "|result_submit|hitl_request|hitl_resolve|workflow_create|workflow_modify"
                    + "|employee_invite|employee_remove|agent_deregister|log_read|system_config"
                    + "|org_manage|console_admin|\\*") String> capabilities,
            @Pattern(regexp = "self|team|global") String dataScope,
            @Min(0) @Max(720) Integer expiresInHours
    ) {
    }

    public record InviteOut(String inviteCode, String accountType, String teamId,
                            String positionId, String dataScope, List<String> capabilities,
                            Instant expiresAt) {
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
            List<String> capabilities,
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

    public record SeatAssignIn(String seatId) {
    }

    public record EndpointReviewIn(@NotNull Boolean approved) {
    }

    public record ManagerIn(@NotNull Boolean enabled) {
    }

    public record AgentBindIn(String agentId) {
    }

    public record DeregisterIn(String reason) {
    }

    public record LogoutIn() {
    }
}
