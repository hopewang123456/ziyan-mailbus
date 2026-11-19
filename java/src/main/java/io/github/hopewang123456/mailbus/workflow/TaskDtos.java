package io.github.hopewang123456.mailbus.workflow;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

public final class TaskDtos {

    private TaskDtos() {
    }

    public record TaskIn(@NotBlank @Size(max = 64) String title, String ownerId,
                         String workflowId, Integer workflowVersion) {
    }

    public record TaskAdvanceIn(String nodeId,
                                @Pattern(regexp = "running|done|failed|blocked|skipped")
                                String outcome,
                                String note) {
    }

    public record TaskNodeOut(String nodeId, String name, int order, String state) {
    }

    public record TaskOut(String taskId, String title, String state, String workflowId,
                          Integer workflowVersion, String ownerId, String createdBy,
                          Instant createdAt, Instant updatedAt, List<TaskNodeOut> nodes) {
    }
}
