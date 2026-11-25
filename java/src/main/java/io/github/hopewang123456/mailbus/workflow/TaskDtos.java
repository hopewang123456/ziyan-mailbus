package io.github.hopewang123456.mailbus.workflow;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class TaskDtos {

    private TaskDtos() {
    }

    public record TaskCreateIn(@NotBlank @Size(max = 64) String title, String ownerId,
                               String workflowId, Map<String, String> variables) {
    }

    public record ResultIn(@NotNull @Min(1) Integer attemptNo, @NotBlank String result,
                           List<String> artifactIds) {
    }

    public record CancelIn(@Size(min = 1, max = 64) String reason) {
    }

    public record RerunJoinIn(@NotBlank @Size(max = 64) String fanoutGroup,
                              @Pattern(regexp = "join|downstream") String scope) {
    }

    public record TaskRunOut(String runId, String nodeId, int attemptNo, int fanoutSlot,
                             String state, String assignedEmployeeId, String fanoutGroup,
                             Instant dispatchedAt, Instant startedAt, Instant completedAt,
                             String result) {
    }

    public record TaskNodeOut(String nodeId, String name, int seq, String state,
                              String currentRunId, List<TaskRunOut> runs) {
    }

    public record TaskDetailOut(String taskId, String title, String state, String ownerId,
                                String createdBy, String workflowId, Integer workflowVersion,
                                String terminationReason, Instant createdAt, Instant updatedAt,
                                List<TaskNodeOut> nodes, List<TaskRunOut> runs,
                                List<ArtifactOut> artifacts) {
    }

    public record ArtifactOut(String artifactId, String taskId, String nodeId, String runId,
                              String fileName, String artifactType, String description,
                              Long sizeBytes, String createdBy, Instant createdAt) {
    }

    public record TaskSummaryOut(String taskId, String title, String state, String ownerId,
                                 String workflowId, Integer workflowVersion, Instant createdAt,
                                 Instant updatedAt, String currentNode, int progressDone,
                                 int progressTotal, boolean claimable) {
    }

    public record TaskListOut(List<TaskSummaryOut> items, int total, int limit, int offset) {
    }

    public record TaskCountersOut(int claimable, int mineOpen, int approvals) {
    }

    public record TaskTraceEventOut(Instant at, String kind, String nodeId, String runId,
                                    Integer attemptNo, Map<String, Object> detail) {
    }

    public record TaskTraceOut(String taskId, List<TaskTraceEventOut> events) {
    }

    public record PublicTaskNodeOut(String name, int seq, String state) {
    }

    /** 公开协同任务投影：不暴露创建者、负责人、流程标识与内部节点 ID。 */
    public record PublicTaskOut(String taskId, String title, String state,
                                Instant createdAt, Instant updatedAt,
                                List<PublicTaskNodeOut> nodes) {

        public static PublicTaskOut of(TaskDetailOut task) {
            return new PublicTaskOut(task.taskId(), task.title(), task.state(),
                    task.createdAt(), task.updatedAt(),
                    task.nodes().stream()
                            .map(node -> new PublicTaskNodeOut(node.name(), node.seq(),
                                    node.state()))
                            .toList());
        }
    }
}
