package io.github.hopewang123456.mailbus.workflow;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Service
public class TaskService {

    private static final Set<String> TERMINAL_TASKS = Set.of("done", "failed", "cancelled");
    private static final Set<String> TERMINAL_NODES = Set.of("done", "failed", "skipped");
    private static final Set<String> ACTIVE_NODES = Set.of("pending", "dispatched", "running", "blocked");

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;
    private final WorkflowService workflows;

    public TaskService(JdbcTemplate jdbc, Ids ids, Outbox outbox, WorkflowService workflows) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
        this.workflows = workflows;
    }

    public List<TaskDtos.TaskOut> list(String state, String ownerId) {
        if (state != null && !state.isBlank()) {
            return jdbc.query("SELECT * FROM task_tasks WHERE state = ? AND (? IS NULL OR owner_id = ?)"
                            + " ORDER BY created_at",
                    this::mapTask, state, blankToNull(ownerId), blankToNull(ownerId))
                    .stream().map(this::withNodes).toList();
        }
        return jdbc.query("SELECT * FROM task_tasks WHERE (? IS NULL OR owner_id = ?)"
                        + " ORDER BY created_at",
                this::mapTask, blankToNull(ownerId), blankToNull(ownerId))
                .stream().map(this::withNodes).toList();
    }

    public TaskDtos.TaskOut get(String taskId) {
        return withNodes(load(taskId));
    }

    @Transactional
    public TaskDtos.TaskOut create(Actor actor, TaskDtos.TaskIn input) {
        String ownerId = input.ownerId() == null || input.ownerId().isBlank()
                ? actor.employeeId() : input.ownerId();
        Authz.ensureAllowed(actor, Authz.TASK_CREATE, Authz.Resource.owned("task", ownerId));
        WorkflowDtos.VersionOut version = version(input.workflowId(), input.workflowVersion());
        Instant now = Instant.now();
        TaskRow task = new TaskRow(ids.next("task"), title(input.title()), "draft",
                version == null ? null : version.workflowId(),
                version == null ? null : version.version(), ownerId, actor.employeeId(),
                now, now);
        List<NodeRow> nodes = new ArrayList<>();
        if (version != null) {
            for (WorkflowDtos.VersionNodeOut node : version.nodes()) {
                nodes.add(new NodeRow(task.taskId(), node.nodeId(), node.name(), node.order(),
                        "pending", now));
            }
        }
        save(task, nodes);
        outbox.enqueue("task.created", java.util.Map.of("task_id", task.taskId()));
        return withNodes(task);
    }

    @Transactional
    public TaskDtos.TaskOut dispatch(Actor actor, String taskId) {
        TaskRow task = load(taskId);
        Authz.ensureAllowed(actor, Authz.TASK_DISPATCH, Authz.Resource.owned("task", task.ownerId()));
        if (!"draft".equals(task.state()) && !"queued".equals(task.state())) {
            throw ApiException.conflict("invalid_transition", "只有草稿或排队中的任务可以派发");
        }
        Instant now = Instant.now();
        TaskRow queued = task.withState("queued", now);
        List<NodeRow> nodes = nodes(taskId);
        if (task.workflowVersion() != null) {
            nodes = dispatchNext(nodes, now);
        }
        save(queued, nodes);
        outbox.enqueue("task.dispatched", java.util.Map.of("task_id", taskId));
        return withNodes(queued);
    }

    @Transactional
    public TaskDtos.TaskOut advance(Actor actor, String taskId, TaskDtos.TaskAdvanceIn input) {
        TaskRow task = load(taskId);
        Authz.ensureAllowed(actor, Authz.RESULT_SUBMIT, Authz.Resource.owned("task", task.ownerId()));
        if (TERMINAL_TASKS.contains(task.state())) {
            throw ApiException.conflict("invalid_transition", "任务已结束，不能继续推进");
        }
        String outcome = input.outcome() == null ? "running" : input.outcome();
        if (!Set.of("running", "done", "failed", "blocked", "skipped").contains(outcome)) {
            throw ApiException.conflict("invalid_state", "未知推进动作：" + outcome);
        }
        Instant now = Instant.now();
        List<NodeRow> nodes = nodes(taskId);
        TaskRow updated;
        if (task.workflowVersion() == null) {
            updated = advanceFree(task, outcome, now);
        } else {
            updated = advanceWorkflow(task, nodes, input.nodeId(), outcome, now);
        }
        save(updated, nodes);
        outbox.enqueue("task.advanced", java.util.Map.of("task_id", taskId,
                "state", updated.state()));
        return withNodes(updated);
    }

    @Transactional
    public TaskDtos.TaskOut cancel(Actor actor, String taskId) {
        TaskRow task = load(taskId);
        Authz.ensureAllowed(actor, Authz.TASK_DISPATCH, Authz.Resource.owned("task", task.ownerId()));
        if (TERMINAL_TASKS.contains(task.state())) {
            return withNodes(task);
        }
        Instant now = Instant.now();
        TaskRow cancelled = task.withState("cancelled", now);
        List<NodeRow> nodes = nodes(taskId).stream()
                .map(node -> TERMINAL_NODES.contains(node.state()) ? node : node.withState("skipped", now))
                .toList();
        save(cancelled, nodes);
        outbox.enqueue("task.cancelled", java.util.Map.of("task_id", taskId));
        return withNodes(cancelled);
    }

    @Transactional
    public void hold(String taskId, String reason) {
        TaskRow task = load(taskId);
        if (TERMINAL_TASKS.contains(task.state())) {
            throw ApiException.conflict("invalid_transition", "任务已结束，不能阻塞");
        }
        Instant now = Instant.now();
        TaskRow blocked = task.withState("blocked", now);
        List<NodeRow> nodes = nodes(taskId).stream()
                .map(node -> Set.of("dispatched", "running").contains(node.state())
                        ? node.withState("blocked", now) : node)
                .toList();
        save(blocked, nodes);
        outbox.enqueue("task.blocked", java.util.Map.of("task_id", taskId, "reason", reason));
    }

    @Transactional
    public void resume(String taskId) {
        TaskRow task = load(taskId);
        if (!"blocked".equals(task.state())) {
            throw ApiException.conflict("invalid_transition", "只有阻塞中的任务可以恢复");
        }
        Instant now = Instant.now();
        TaskRow running = task.withState("running", now);
        List<NodeRow> nodes = nodes(taskId).stream()
                .map(node -> "blocked".equals(node.state()) ? node.withState("running", now) : node)
                .toList();
        save(running, nodes);
        outbox.enqueue("task.resumed", java.util.Map.of("task_id", taskId));
    }

    @Transactional
    public void fail(String taskId, String reason) {
        TaskRow task = load(taskId);
        if ("failed".equals(task.state())) {
            return;
        }
        if (TERMINAL_TASKS.contains(task.state())) {
            throw ApiException.conflict("invalid_transition", "任务已结束，不能标记失败");
        }
        Instant now = Instant.now();
        TaskRow failed = task.withState("failed", now);
        List<NodeRow> nodes = nodes(taskId).stream()
                .map(node -> TERMINAL_NODES.contains(node.state()) ? node : node.withState("failed", now))
                .toList();
        save(failed, nodes);
        outbox.enqueue("task.failed", java.util.Map.of("task_id", taskId, "reason", reason));
    }

    private WorkflowDtos.VersionOut version(String workflowId, Integer requested) {
        if (workflowId == null || workflowId.isBlank()) {
            return null;
        }
        WorkflowDtos.WorkflowOut definition = workflows.loadDefinition(workflowId);
        Integer number = requested != null ? requested : definition.publishedVersion();
        if (number == null) {
            throw ApiException.domain("version_not_published", "流程尚未发布版本");
        }
        WorkflowDtos.VersionOut version = workflows.loadVersion(workflowId, number);
        if (!"published".equals(version.state())) {
            throw ApiException.domain("version_not_published", "只能从已发布版本创建任务");
        }
        return version;
    }

    private TaskRow advanceFree(TaskRow task, String outcome, Instant now) {
        Set<String> allowed = switch (outcome) {
            case "running" -> Set.of("draft", "queued", "running", "blocked");
            case "done" -> Set.of("queued", "running");
            case "failed" -> Set.of("draft", "queued", "running");
            case "blocked" -> Set.of("queued", "running");
            case "skipped" -> Set.of("draft", "queued", "running", "blocked");
            default -> Set.of();
        };
        if (!allowed.contains(task.state())) {
            throw ApiException.conflict("invalid_transition",
                    "任务状态 " + task.state() + " 不能执行 " + outcome);
        }
        String target = switch (outcome) {
            case "done" -> "done";
            case "failed" -> "failed";
            case "blocked" -> "blocked";
            case "skipped" -> "cancelled";
            default -> "running";
        };
        return task.withState(target, now);
    }

    private TaskRow advanceWorkflow(TaskRow task, List<NodeRow> nodes, String nodeId,
                                    String outcome, Instant now) {
        int index = nodeIndex(nodes, nodeId);
        NodeRow current = nodes.get(index);
        Set<String> allowed = switch (outcome) {
            case "running" -> Set.of("dispatched", "running", "blocked");
            case "done" -> Set.of("dispatched", "running");
            case "failed" -> Set.of("dispatched", "running");
            case "blocked" -> Set.of("dispatched", "running");
            case "skipped" -> Set.of("pending", "dispatched", "running", "blocked");
            default -> Set.of();
        };
        if (!allowed.contains(current.state())) {
            throw ApiException.conflict("invalid_transition",
                    "节点状态 " + current.state() + " 不能执行 " + outcome);
        }
        String nodeTarget = "running".equals(outcome) ? "running"
                : "done".equals(outcome) ? "done"
                : "failed".equals(outcome) ? "failed"
                : "blocked".equals(outcome) ? "blocked" : "skipped";
        nodes.set(index, current.withState(nodeTarget, now));
        if ("done".equals(outcome) || "skipped".equals(outcome)) {
            dispatchNext(nodes, now);
        }
        String state;
        if ("failed".equals(outcome)) {
            state = "failed";
        } else if ("blocked".equals(outcome)) {
            state = "blocked";
        } else if ("running".equals(outcome)) {
            state = "running";
        } else if (nodes.stream().anyMatch(node -> ACTIVE_NODES.contains(node.state()))) {
            state = "running";
        } else if (nodes.stream().anyMatch(node -> "failed".equals(node.state()))) {
            state = "failed";
        } else {
            state = "done";
        }
        return task.withState(state, now);
    }

    private int nodeIndex(List<NodeRow> nodes, String nodeId) {
        if (nodeId != null) {
            for (int index = 0; index < nodes.size(); index++) {
                if (nodes.get(index).nodeId().equals(nodeId)) {
                    return index;
                }
            }
            throw ApiException.notFound("任务节点不存在");
        }
        for (int index = 0; index < nodes.size(); index++) {
            if (Set.of("dispatched", "running", "blocked").contains(nodes.get(index).state())) {
                return index;
            }
        }
        for (int index = 0; index < nodes.size(); index++) {
            if ("pending".equals(nodes.get(index).state())) {
                return index;
            }
        }
        throw ApiException.conflict("invalid_state", "任务没有可推进的节点");
    }

    private List<NodeRow> dispatchNext(List<NodeRow> nodes, Instant now) {
        if (nodes.stream().anyMatch(node ->
                Set.of("dispatched", "running", "blocked").contains(node.state()))) {
            return nodes;
        }
        for (int index = 0; index < nodes.size(); index++) {
            if ("pending".equals(nodes.get(index).state())) {
                nodes.set(index, nodes.get(index).withState("dispatched", now));
                break;
            }
        }
        return nodes;
    }

    private TaskRow load(String taskId) {
        List<TaskRow> rows = jdbc.query("SELECT * FROM task_tasks WHERE task_id = ?",
                this::mapTask, taskId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("任务不存在"));
    }

    private List<NodeRow> nodes(String taskId) {
        return jdbc.query("SELECT * FROM task_nodes WHERE task_id = ? ORDER BY seq",
                (row, index) -> new NodeRow(taskId, row.getString("node_id"),
                        row.getString("name"), row.getInt("seq"), row.getString("state"),
                        Instant.ofEpochSecond((long) row.getDouble("updated_at"))), taskId);
    }

    private TaskRow mapTask(java.sql.ResultSet row, int index) throws java.sql.SQLException {
        int workflowVersion = row.getInt("workflow_version");
        boolean versionNull = row.wasNull();
        return new TaskRow(row.getString("task_id"), row.getString("title"),
                row.getString("state"), row.getString("workflow_id"),
                versionNull ? null : workflowVersion, row.getString("owner_id"),
                row.getString("created_by"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                Instant.ofEpochSecond((long) row.getDouble("updated_at")));
    }

    private TaskDtos.TaskOut withNodes(TaskRow task) {
        return new TaskDtos.TaskOut(task.taskId(), task.title(), task.state(),
                task.workflowId(), task.workflowVersion(), task.ownerId(), task.createdBy(),
                task.createdAt(), task.updatedAt(),
                nodes(task.taskId()).stream().map(node -> new TaskDtos.TaskNodeOut(
                        node.nodeId(), node.name(), node.order(), node.state())).toList());
    }

    private void save(TaskRow task, List<NodeRow> nodes) {
        jdbc.update("""
                INSERT INTO task_tasks
                    (task_id, title, state, workflow_id, workflow_version, owner_id, created_by,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (task_id) DO UPDATE SET
                    title = excluded.title, state = excluded.state,
                    workflow_id = excluded.workflow_id,
                    workflow_version = excluded.workflow_version,
                    owner_id = excluded.owner_id, updated_at = excluded.updated_at
                """, task.taskId(), task.title(), task.state(), task.workflowId(),
                task.workflowVersion(), task.ownerId(), task.createdBy(),
                task.createdAt().getEpochSecond(), task.updatedAt().getEpochSecond());
        jdbc.update("DELETE FROM task_nodes WHERE task_id = ?", task.taskId());
        for (NodeRow node : nodes) {
            jdbc.update("""
                    INSERT INTO task_nodes (task_id, node_id, name, seq, state, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, node.taskId(), node.nodeId(), node.name(), node.order(), node.state(),
                    node.updatedAt().getEpochSecond());
        }
    }

    private String title(String value) {
        String title = value == null ? "" : value.strip();
        if (title.isEmpty() || title.length() > 64) {
            throw ApiException.conflict("invalid_state", "任务标题不能为空且不能超过 64 个字符");
        }
        return title;
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private record TaskRow(String taskId, String title, String state, String workflowId,
                           Integer workflowVersion, String ownerId, String createdBy,
                           Instant createdAt, Instant updatedAt) {
        TaskRow withState(String next, Instant now) {
            return new TaskRow(taskId, title, next, workflowId, workflowVersion, ownerId,
                    createdBy, createdAt, now);
        }
    }

    private record NodeRow(String taskId, String nodeId, String name, int order, String state,
                           Instant updatedAt) {
        NodeRow withState(String next, Instant now) {
            return new NodeRow(taskId, nodeId, name, order, next, now);
        }
    }
}
