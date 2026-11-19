package io.github.hopewang123456.mailbus.workflow;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;

public final class ApprovalDtos {

    private ApprovalDtos() {
    }

    public record ApprovalIn(@NotBlank String taskId, @NotBlank @Size(max = 64) String title,
                             @NotBlank @Pattern(regexp = "blocking|advisory|informational")
                             String tier,
                             String nodeId, String note,
                             @Min(1) Integer timeoutMinutes) {
    }

    public record ResolveIn(@NotNull Boolean approved, String note) {
    }

    public record ApprovalOut(String approvalId, String taskId, String nodeId, String title,
                              String tier, String status, String requesterId, String note,
                              Instant createdAt, Instant expiresAt, String resolvedBy,
                              Instant resolvedAt, String resolutionNote) {
    }
}
