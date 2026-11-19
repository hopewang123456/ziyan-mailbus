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

    public List<ApprovalDtos.ApprovalOut> list(String status, String taskId) {
        if (status != null && !status.isBlank()) {
            return jdbc.query("""
                    SELECT * FROM approval_items WHERE status = ? AND (? IS NULL OR task_id = ?)
                     ORDER BY created_at
                    """, this::map, status, blankToNull(taskId), blankToNull(taskId));
        }
        return jdbc.query("""
                SELECT * FROM approval_items WHERE (? IS NULL OR task_id = ?) ORDER BY created_at
                """, this::map, blankToNull(taskId), blankToNull(taskId));
    }

    public ApprovalDtos.ApprovalOut get(String approvalId) {
        return load(approvalId);
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
        return load(approvalId);
    }

    @Transactional
    public ApprovalDtos.ApprovalOut resolve(Actor actor, String approvalId,
                                            ApprovalDtos.ResolveIn input) {
        Authz.require(actor, Authz.HITL_RESOLVE);
        ApprovalDtos.ApprovalOut item = load(approvalId);
        if ("acknowledged".equals(item.status())) {
            throw ApiException.conflict("invalid_transition", "信息档审批无需裁决");
        }
        if ("expired".equals(item.status())) {
            throw ApiException.conflict("invalid_transition", "审批已超时");
        }
        boolean approved = Boolean.TRUE.equals(input.approved());
        if ("approved".equals(item.status()) || "rejected".equals(item.status())) {
            if (("approved".equals(item.status())) == approved) {
                return item;
            }
            throw ApiException.conflict("invalid_transition", "审批已裁决");
        }
        Instant now = Instant.now();
        String status = approved ? "approved" : "rejected";
        jdbc.update("""
                UPDATE approval_items SET status = ?, resolved_by = ?, resolved_at = ?,
                    resolution_note = ? WHERE approval_id = ?
                """, status, actor.employeeId(), now.getEpochSecond(), input.note(), approvalId);
        if ("blocking".equals(item.tier())) {
            if (approved) {
                tasks.resume(item.taskId());
            } else {
                tasks.fail(item.taskId(), "approval_rejected");
            }
        }
        outbox.enqueue(approved ? "approval.approved" : "approval.rejected",
                java.util.Map.of("approval_id", approvalId, "task_id", item.taskId(),
                        "resolver_id", actor.employeeId()));
        return load(approvalId);
    }

    @Transactional
    public int sweepExpired() {
        Instant now = Instant.now();
        List<ApprovalDtos.ApprovalOut> due = jdbc.query("""
                SELECT * FROM approval_items WHERE status = 'pending' AND expires_at <= ?
                """, this::map, now.getEpochSecond());
        for (ApprovalDtos.ApprovalOut item : due) {
            jdbc.update("UPDATE approval_items SET status = 'expired', resolved_at = ?"
                    + " WHERE approval_id = ?", now.getEpochSecond(), item.approvalId());
            if ("blocking".equals(item.tier())) {
                try {
                    tasks.hold(item.taskId(), "approval_timeout");
                } catch (ApiException ignored) {
                    // 任务已结束或已阻塞时保持现状
                }
            }
            outbox.enqueue("approval.expired", java.util.Map.of("approval_id", item.approvalId(),
                    "task_id", item.taskId(), "tier", item.tier()));
        }
        return due.size();
    }

    private ApprovalDtos.ApprovalOut load(String approvalId) {
        List<ApprovalDtos.ApprovalOut> rows = jdbc.query(
                "SELECT * FROM approval_items WHERE approval_id = ?", this::map, approvalId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("审批不存在"));
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
