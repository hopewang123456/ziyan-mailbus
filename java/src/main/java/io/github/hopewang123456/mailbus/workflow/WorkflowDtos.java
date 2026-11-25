package io.github.hopewang123456.mailbus.workflow;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class WorkflowDtos {

    private WorkflowDtos() {
    }

    public record WorkflowIn(@NotBlank @Size(max = 64) String name,
                             @Valid WorkflowGraph graph) {
    }

    public record WorkflowOut(String workflowId, String name, int latestVersion,
                              Integer publishedVersion, Instant createdAt,
                              Instant updatedAt) {
    }

    public record WorkflowListOut(List<WorkflowOut> items, int total, int limit, int offset) {
    }

    public record VersionNodeIn(@NotBlank @Size(max = 64) String name) {
    }

    public record VersionIn(@NotEmpty List<VersionNodeIn> nodes) {
    }

    public record VersionNodeOut(String nodeId, String name, int order) {
    }

    /** 旧别名 POST /versions 的响应；契约内版本列表不再返回 nodes。 */
    public record VersionOut(String workflowId, int version, String state,
                             List<VersionNodeOut> nodes, Instant createdAt,
                             Instant publishedAt) {
    }

    public record ContractVersionOut(String workflowId, int version, String state,
                                     int revision, Instant createdAt,
                                     Instant publishedAt) {
    }

    public record VersionListOut(List<ContractVersionOut> items, int total, int limit,
                                 int offset) {
    }

    public record GraphNode(@NotBlank @Size(max = 64) String nodeId,
                            @NotBlank @Size(max = 64) String name,
                            @NotBlank
                            @Pattern(regexp = "start|agent|human|condition|parallel_join"
                                    + "|final_approval") String nodeType,
                            String positionId,
                            @Min(0) int seq,
                            String promptTemplate,
                            List<String> needsArtifactsFrom,
                            @Min(0) int maxRetries,
                            @Min(0) int maxLoops,
                            @Min(0) Integer timeoutSeconds,
                            Map<String, Object> config,
                            double posX,
                            double posY) {
    }

    public record GraphEdge(@NotBlank @Size(max = 64) String fromNodeId,
                            @NotBlank @Size(max = 64) String toNodeId,
                            String condition) {
    }

    public record WorkflowGraph(@Valid List<GraphNode> nodes, @Valid List<GraphEdge> edges) {
    }

    public record GraphIn(@NotNull @Valid WorkflowGraph graph, @Min(1) int revision) {
    }

    public record GraphOut(WorkflowGraph graph, int revision) {
    }

    public record EdgeRefOut(String fromNodeId, String toNodeId) {
    }

    public record ValidateIssueOut(String code, String messageZh, String nodeId,
                                   EdgeRefOut edge) {
    }

    public record ValidateOut(boolean ok, List<ValidateIssueOut> errors,
                              List<ValidateIssueOut> warnings,
                              Map<String, Object> stats) {
    }
}
