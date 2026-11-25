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
import java.util.List;
import java.util.Set;

@Service
public class ApprovalService {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;
    private final TaskService tasks;

    public ApprovalService(JdbcTemplate jdbc, Ids ids, Outbox outbox, TaskService tasks) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
        this.tasks = tasks;
    }

    public ApprovalDtos.ApprovalListOut list(Actor actor, String state, int limit, int offset) {
        java.util.List<TaskRepository.ApprovalRow> rows =
                tasks.listApprovals(actor, state, limit, offset);
        int total = tasks.countApprovals(actor, state);
        return new ApprovalDtos.ApprovalListOut(rows.stream().map(this::view).toList(),
                total, limit, offset);
    }

    public ApprovalDtos.ApprovalOut get(String approvalId) {
        List<ApprovalDtos.ApprovalOut> rows = jdbc.query(
                "SELECT * FROM approval_items WHERE approval_id = ?", this::map, approvalId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("审批不存在"));
    }

    @Transactional
    public ApprovalDtos.ApprovalOut request(Actor actor, ApprovalDtos.ApprovalIn input) {
        TaskServiceRef task = taskRef(input.taskId());
        Authz.ensureAllowed(actor, Authz.HITL_REQUEST, Authz.Resource.owned("task", task.ownerId()));
        String tier = input.tier();
        if (!Set.of("blocking", "advisory", "informational").contains(tier)) {
            throw ApiException.conflict("invalid_state", "未知审批档位：" + tier);
        }
        String title = input.title() == null ? "" : input.title().strip();
        if (title.isEmpty() || title.length() > 64) {
            throw ApiException.conflict("invalid_state", "审批标题不能为空且不能超过 64 个字符");
        }
        int minutes = input.timeoutMinutes() == null ? 30 : input.timeoutMinutes();
        if (minutes <= 0) {
            throw ApiException.conflict("invalid_state", "审批超时时间必须大于 0");
        }
        Instant now = Instant.now();
        String approvalId = ids.next("appr");
        boolean informational = "informational".equals(tier);
        String status = informational ? "acknowledged" : "pending";
        jdbc.update("""
                INSERT INTO approval_items
                    (approval_id, task_id, node_id, title, tier, status, requester_id, note,
                     created_at, expires_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, approvalId, input.taskId(), input.nodeId(), title, tier, status,
                actor.employeeId(), input.note(), now.getEpochSecond(),
                now.plusSeconds(minutes * 60L).getEpochSecond(),
                informational ? now.getEpochSecond() : null);
        if ("blocking".equals(tier)) {
            tasks.hold(input.taskId(), "approval_requested");
        }
        outbox.enqueue("approval.requested", java.util.Map.of("approval_id", approvalId,
                "task_id", input.taskId(), "tier", tier, "status", status));
        return get(approvalId);
    }

    @Transactional
    public ApprovalDtos.ApprovalOut resolve(Actor actor, String approvalId,
                                            ApprovalDtos.ResolveIn input) {
        TaskRepository.ApprovalRow item =
                tasks.resolveApproval(actor, approvalId, input.decision(), input.comment());
        return view(item);
    }

    /** 撤回审批：发起人或超管可撤回；仅待裁决可撤，阻塞档在任务仍阻塞时恢复执行。 */
    @Transactional
    public void withdraw(Actor actor, String approvalId) {
        ApprovalDtos.ApprovalOut item = get(approvalId);
        if (!actor.employeeId().equals(item.requesterId())) {
            Authz.require(actor, Authz.SYSTEM_CONFIG);
        }
        if (!"pending".equals(item.status())) {
            throw ApiException.conflict("invalid_transition", "只有待裁决审批可以撤回");
        }
        Instant now = Instant.now();
        jdbc.update("""
                UPDATE approval_items SET status = 'withdrawn', resolved_by = ?, resolved_at = ?
                 WHERE approval_id = ?
                """, actor.employeeId(), now.getEpochSecond(), approvalId);
        if ("blocking".equals(item.tier()) && "blocked".equals(taskState(item.taskId()))) {
            tasks.resume(item.taskId());
        }
        outbox.enqueue("approval.withdrawn", java.util.Map.of(
                "approval_id", approvalId, "task_id", item.taskId(),
                "tier", item.tier(), "actor_id", actor.employeeId()));
    }

    private ApprovalDtos.ApprovalOut view(TaskRepository.ApprovalRow row) {
        return new ApprovalDtos.ApprovalOut(row.approvalId(), row.taskId(), row.nodeId(),
                row.title(), row.tier(), row.status(), row.requesterId(), row.note(),
                row.createdAt(), row.expiresAt(), row.resolvedBy(), row.resolvedAt(),
                row.resolutionNote());
    }

    private String taskState(String taskId) {
        List<String> states = jdbc.query("SELECT state FROM task_tasks WHERE task_id = ?",
                (row, index) -> row.getString("state"), taskId);
        return states.stream().findFirst().orElse(null);
    }

    private TaskServiceRef taskRef(String taskId) {
        List<TaskServiceRef> rows = jdbc.query(
                "SELECT task_id, owner_id, state FROM task_tasks WHERE task_id = ?",
                (row, index) -> new TaskServiceRef(row.getString("task_id"),
                        row.getString("owner_id"), row.getString("state")), taskId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("任务不存在"));
    }

    private ApprovalDtos.ApprovalOut map(java.sql.ResultSet row, int index)
            throws java.sql.SQLException {
        return new ApprovalDtos.ApprovalOut(
                row.getString("approval_id"), row.getString("task_id"),
                row.getString("node_id"), row.getString("title"), row.getString("tier"),
                row.getString("status"), row.getString("requester_id"), row.getString("note"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                Instant.ofEpochSecond((long) row.getDouble("expires_at")),
                row.getString("resolved_by"), nullableInstant(row, "resolved_at"),
                row.getString("resolution_note"));
    }

    private Instant nullableInstant(java.sql.ResultSet row, String column)
            throws java.sql.SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private record TaskServiceRef(String taskId, String ownerId, String state) {
    }
}
