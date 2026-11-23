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

    public record PublicTaskNodeOut(String name, int order, String state) {
    }

    /** 公开协同任务投影：不暴露创建者、负责人、流程标识与内部节点 ID。 */
    public record PublicTaskOut(String taskId, String title, String state,
                                Instant createdAt, Instant updatedAt,
                                List<PublicTaskNodeOut> nodes) {

        public static PublicTaskOut of(TaskOut task) {
            return new PublicTaskOut(task.taskId(), task.title(), task.state(),
                    task.createdAt(), task.updatedAt(),
                    task.nodes().stream()
                            .map(node -> new PublicTaskNodeOut(
                                    node.name(), node.order(), node.state()))
                            .toList());
        }
    }
}
