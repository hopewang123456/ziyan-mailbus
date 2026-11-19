package io.github.hopewang123456.mailbus.workflow;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;

public final class WorkflowDtos {

    private WorkflowDtos() {
    }

    public record WorkflowIn(@NotBlank @Size(max = 64) String name) {
    }

    public record WorkflowOut(String workflowId, String name, int latestVersion,
                              Integer publishedVersion, Instant createdAt) {
    }

    public record VersionNodeIn(@NotBlank @Size(max = 64) String name) {
    }

    public record VersionIn(@NotEmpty List<VersionNodeIn> nodes) {
    }

    public record VersionNodeOut(String nodeId, String name, int order) {
    }

    public record VersionOut(String workflowId, int version, String state,
                             List<VersionNodeOut> nodes, Instant createdAt,
                             Instant publishedAt) {
    }
}
