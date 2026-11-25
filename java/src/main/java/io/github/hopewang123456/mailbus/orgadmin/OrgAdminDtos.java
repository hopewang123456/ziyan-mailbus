package io.github.hopewang123456.mailbus.orgadmin;

import io.github.hopewang123456.mailbus.identity.IdentityDtos;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

/** 组织域契约 DTO：与 shared/contracts/generated/openapi.json 保持一致。 */
public final class OrgAdminDtos {

    private OrgAdminDtos() {
    }

    public record EmployeeListOut(List<IdentityDtos.EmployeeView> items, int total, int limit,
                                  int offset) {
    }

    public record EmployeeInviteIn(
            @NotBlank @Size(max = 64) String displayName,
            String positionId,
            String teamId,
            @Pattern(regexp = "self|team|global") String dataScope,
            List<String> permissions,
            @Min(1) @Max(720) Integer expiresInHours
    ) {
    }

    public record PermissionsIn(List<String> permissions) {
    }

    public record PermissionsOut(String employeeId, List<String> permissions) {
    }

    public record RolesIn(List<String> roleIds) {
    }

    public record RolesOut(String employeeId, List<String> roleIds) {
    }

    public record CapabilitiesIn(List<String> capabilities) {
    }

    public record CapabilitiesOut(String employeeId, List<String> capabilities) {
    }

    public record PositionIn(@NotBlank @Size(max = 64) String name, List<String> capabilities) {
    }

    public record PositionOut(String positionId, String name, List<String> capabilities,
                              List<String> roleIds, Instant createdAt) {
    }

    public record PositionListOut(List<PositionOut> items, int total, int limit, int offset) {
    }

    public record RoleIn(@NotBlank @Size(max = 64) String name, List<String> capabilities,
                         String description, Boolean enabled, String icon, String color) {
    }

    public record RoleOut(String roleId, String name, List<String> capabilities,
                          String description, boolean enabled, String icon, String color,
                          Instant createdAt, Instant updatedAt) {
    }

    public record RoleListOut(List<RoleOut> items, int total, int limit, int offset) {
    }

    public record BindingIn(List<String> ids) {
    }

    public record TeamIn(@NotBlank @Size(max = 64) String name, String leaderEmployeeId) {
    }

    public record TeamOut(String teamId, String name, String leaderEmployeeId, Instant createdAt) {
    }

    public record TeamListOut(List<TeamOut> items, int total, int limit, int offset) {
    }

    public record SeatOut(String seatId, String teamId, String positionId, String employeeId,
                          String agentId, Double x, Double y, Double rotation) {
    }

    public record SeatListOut(List<SeatOut> items, int total, int limit, int offset) {
    }

    public record SeatAssignIn(String employeeId, String teamId, String positionId) {
    }

    public record OptionOut(String optionId, String label, boolean enabled) {
    }

    public record OptionListOut(List<OptionOut> items, int total, int limit, int offset) {
    }

    public record InviteOut(String inviteId, String inviteCode, String accountType, String teamId,
                            String positionId, String dataScope, List<String> permissions,
                            String createdBy, Instant createdAt, Instant expiresAt,
                            Instant consumedAt, Instant revokedAt) {
    }

    public record InviteAcceptIn(@NotBlank @Size(max = 128) String inviteCode,
                                 @Size(max = 64) String displayName) {
    }

    public record InviteAcceptOut(IdentityDtos.EmployeeView employee, String token) {
    }
}
