package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 任务域仓储：task_tasks / task_nodes / task_node_runs / 产物 / 升级 / 变量 / 审批读取。 */
@Repository
public class TaskRepository {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public TaskRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public record TaskRow(String taskId, String title, String state, String workflowId,
                          Integer workflowVersion, String ownerId, String createdBy,
                          String terminationReason, Map<String, Integer> loopCounters,
                          Instant createdAt, Instant updatedAt) {

        public TaskRow withState(String next, Instant now) {
            return new TaskRow(taskId, title, next, workflowId, workflowVersion, ownerId,
                    createdBy, terminationReason, loopCounters, createdAt, now);
        }

        public TaskRow withTermination(String reason, Instant now) {
            return new TaskRow(taskId, title, state, workflowId, workflowVersion, ownerId,
                    createdBy, reason, loopCounters, createdAt, now);
        }

        public TaskRow withLoopCounters(Map<String, Integer> counters, Instant now) {
            return new TaskRow(taskId, title, state, workflowId, workflowVersion, ownerId,
                    createdBy, terminationReason, counters, createdAt, now);
        }

        public TaskRow withOwner(String nextOwner, Instant now) {
            return new TaskRow(taskId, title, state, workflowId, workflowVersion, nextOwner,
                    createdBy, terminationReason, loopCounters, createdAt, now);
        }
    }

    public record NodeRow(String taskId, String nodeId, String name, int seq, String state,
                          String currentRunId, Instant updatedAt) {

        public NodeRow withState(String next, String runId, Instant now) {
            return new NodeRow(taskId, nodeId, name, seq, next, runId, now);
        }
    }

    public record RunRow(String runId, String taskId, String nodeId, int attemptNo,
                         int fanoutSlot, String assignedEmployeeId, String roleId, String state,
                         String fanoutGroup, boolean shortFanout, String result,
                         String parentRunId, Instant dispatchedAt, Instant startedAt,
                         Instant completedAt, Instant deadlineAt, Instant escalatedAt) {

        public RunRow withState(String next, Instant now) {
            return new RunRow(runId, taskId, nodeId, attemptNo, fanoutSlot, assignedEmployeeId,
                    roleId, next, fanoutGroup, shortFanout, result, parentRunId, dispatchedAt,
                    startedAt, completedAt, deadlineAt, escalatedAt);
        }

        public RunRow withResult(String next, Instant now) {
            return new RunRow(runId, taskId, nodeId, attemptNo, fanoutSlot, assignedEmployeeId,
                    roleId, state, fanoutGroup, shortFanout, next, parentRunId, dispatchedAt,
                    startedAt, completedAt, deadlineAt, escalatedAt);
        }

        public RunRow withEscalatedAt(Instant value) {
            return new RunRow(runId, taskId, nodeId, attemptNo, fanoutSlot, assignedEmployeeId,
                    roleId, state, fanoutGroup, shortFanout, result, parentRunId, dispatchedAt,
                    startedAt, completedAt, deadlineAt, value);
        }

        public RunRow withSubmission(String employeeId, String nextState, Instant start,
                                     Instant complete, String nextResult) {
            return new RunRow(runId, taskId, nodeId, attemptNo, fanoutSlot, employeeId, roleId,
                    nextState, fanoutGroup, shortFanout, nextResult, parentRunId, dispatchedAt,
                    start, complete, deadlineAt, escalatedAt);
        }

        public RunRow retry(String runId, int attemptNo, Instant dispatchedAt,
                            Instant deadlineAt) {
            return new RunRow(runId, taskId, nodeId, attemptNo, fanoutSlot, assignedEmployeeId,
                    roleId, "dispatched", fanoutGroup, shortFanout, null, parentRunId,
                    dispatchedAt, null, null, deadlineAt, null);
        }
    }

    public record ArtifactRow(String artifactId, String taskId, String nodeId, String runId,
                              String filePath, String fileName, String artifactType,
                              String description, String createdBy, Instant createdAt,
                              int version) {
    }

    public record ApprovalRow(String approvalId, String taskId, String nodeId, String title,
                              String tier, String status, String requesterId, String note,
                              Instant createdAt, Instant expiresAt, String resolvedBy,
                              Instant resolvedAt, String resolutionNote) {

        public ApprovalRow resolved(String nextStatus, String resolverId, String nextNote,
                                    Instant at) {
            return new ApprovalRow(approvalId, taskId, nodeId, title, tier, nextStatus,
                    requesterId, note, createdAt, expiresAt, resolverId, at, nextNote);
        }
    }

    // ---- 任务 ----

    public void insertTask(TaskRow task) {
        jdbc.update("""
                INSERT INTO task_tasks (task_id, title, state, workflow_id, workflow_version,
                    owner_id, created_by, created_at, updated_at, termination_reason, loop_counters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (task_id) DO NOTHING
                """, task.taskId(), task.title(), task.state(), task.workflowId(),
                task.workflowVersion(), task.ownerId(), task.createdBy(),
                epoch(task.createdAt()), epoch(task.updatedAt()), task.terminationReason(),
                jsonLoop(task.loopCounters()));
    }

    public void saveTask(TaskRow task) {
        jdbc.update("""
                UPDATE task_tasks SET title = ?, state = ?, owner_id = ?,
                    termination_reason = ?, loop_counters = ?, updated_at = ?
                 WHERE task_id = ?
                """, task.title(), task.state(), task.ownerId(), task.terminationReason(),
                jsonLoop(task.loopCounters()), epoch(task.updatedAt()), task.taskId());
    }

    public TaskRow getTask(String taskId) {
        return jdbc.query("SELECT * FROM task_tasks WHERE task_id = ?", this::mapTask, taskId)
                .stream().findFirst().orElse(null);
    }

    public List<TaskRow> listTasks(String state, String ownerId, String workflowId,
                                   Integer limit, Integer offset, String viewerId) {
        List<Object> params = new ArrayList<>();
        String where = taskFilters(state, ownerId, workflowId, viewerId, params);
        String sql = "SELECT * FROM task_tasks" + where + " ORDER BY created_at, task_id";
        if (limit != null) {
            sql += " LIMIT ? OFFSET ?";
            params.add(limit);
            params.add(offset == null ? 0 : offset);
        }
        return jdbc.query(sql, this::mapTask, params.toArray());
    }

    public int countTasks(String state, String ownerId, String workflowId, String viewerId) {
        List<Object> params = new ArrayList<>();
        String where = taskFilters(state, ownerId, workflowId, viewerId, params);
        Integer value = jdbc.queryForObject("SELECT COUNT(*) FROM task_tasks" + where,
                Integer.class, params.toArray());
        return value == null ? 0 : value;
    }

    public List<NodeRow> nodes(String taskId) {
        return jdbc.query("SELECT * FROM task_nodes WHERE task_id = ? ORDER BY seq",
                this::mapNode, taskId);
    }

    public NodeRow getNode(String taskId, String nodeId) {
        return jdbc.query("SELECT * FROM task_nodes WHERE task_id = ? AND node_id = ?",
                        this::mapNode, taskId, nodeId)
                .stream().findFirst().orElse(null);
    }

    public void saveNode(NodeRow node) {
        jdbc.update("""
                INSERT INTO task_nodes (task_id, node_id, name, seq, state, current_run_id,
                    updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (task_id, node_id) DO UPDATE SET
                    name = excluded.name, seq = excluded.seq, state = excluded.state,
                    current_run_id = excluded.current_run_id, updated_at = excluded.updated_at
                """, node.taskId(), node.nodeId(), node.name(), node.seq(), node.state(),
                node.currentRunId(), epoch(node.updatedAt()));
    }

    // ---- 运行实例 ----

    public void addRun(RunRow run) {
        jdbc.update("""
                INSERT INTO task_node_runs (run_id, task_id, node_id, attempt_no, fanout_slot,
                    assigned_employee_id, role_id, state, fanout_group, short_fanout, result,
                    parent_run_id, dispatched_at, started_at, completed_at, deadline_at,
                    escalated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, run.runId(), run.taskId(), run.nodeId(), run.attemptNo(), run.fanoutSlot(),
                run.assignedEmployeeId(), run.roleId(), run.state(), run.fanoutGroup(),
                run.shortFanout() ? 1 : 0, run.result(), run.parentRunId(),
                epoch(run.dispatchedAt()), epoch(run.startedAt()), epoch(run.completedAt()),
                epoch(run.deadlineAt()), epoch(run.escalatedAt()));
    }

    public void saveRun(RunRow run) {
        jdbc.update("""
                UPDATE task_node_runs SET assigned_employee_id = ?, role_id = ?, state = ?,
                    result = ?, dispatched_at = ?, started_at = ?, completed_at = ?,
                    deadline_at = ?, escalated_at = ?
                 WHERE run_id = ?
                """, run.assignedEmployeeId(), run.roleId(), run.state(), run.result(),
                epoch(run.dispatchedAt()), epoch(run.startedAt()), epoch(run.completedAt()),
                epoch(run.deadlineAt()), epoch(run.escalatedAt()), run.runId());
    }

    public List<RunRow> runsByTask(String taskId) {
        return jdbc.query("SELECT * FROM task_node_runs WHERE task_id = ?"
                + " ORDER BY node_id, fanout_slot, attempt_no", this::mapRun, taskId);
    }

    public RunRow findRun(String runId) {
        return jdbc.query("SELECT * FROM task_node_runs WHERE run_id = ?", this::mapRun, runId)
                .stream().findFirst().orElse(null);
    }

    public List<RunRow> runsByNode(String taskId, String nodeId) {
        return jdbc.query("SELECT * FROM task_node_runs WHERE task_id = ? AND node_id = ?"
                + " ORDER BY fanout_slot, attempt_no", this::mapRun, taskId, nodeId);
    }

    public int maxAttempt(String taskId, String nodeId) {
        Integer value = jdbc.queryForObject("SELECT MAX(attempt_no) FROM task_node_runs"
                + " WHERE task_id = ? AND node_id = ?", Integer.class, taskId, nodeId);
        return value == null ? 0 : value;
    }

    /** CAS 认领：只有 waiting_human 且未分配的执行实例能被抢到。 */
    public boolean claim(String runId, String employeeId, Instant startedAt) {
        return jdbc.update("""
                UPDATE task_node_runs SET assigned_employee_id = ?, state = 'running',
                    started_at = ?
                 WHERE run_id = ? AND state = 'waiting_human'
                   AND assigned_employee_id IS NULL
                """, employeeId, epoch(startedAt), runId) == 1;
    }

    public int countActiveByEmployee(String employeeId) {
        Integer value = jdbc.queryForObject("SELECT COUNT(*) FROM task_node_runs"
                + " WHERE assigned_employee_id = ?"
                + " AND state IN ('dispatched', 'running', 'waiting_human')",
                Integer.class, employeeId);
        return value == null ? 0 : value;
    }

    public List<RunRow> overdueRuns(Instant now, int limit) {
        return jdbc.query("SELECT * FROM task_node_runs WHERE deadline_at IS NOT NULL"
                + " AND deadline_at <= ? AND state IN"
                + " ('pending', 'dispatched', 'running', 'waiting_human')"
                + " ORDER BY deadline_at LIMIT ?", this::mapRun, epoch(now), limit);
    }

    // ---- 产物 ----

    public ArtifactRow getArtifact(String artifactId) {
        return jdbc.query("SELECT * FROM task_node_artifacts WHERE artifact_id = ?",
                        this::mapArtifact, artifactId)
                .stream().findFirst().orElse(null);
    }

    public List<ArtifactRow> listArtifacts(String taskId) {
        return jdbc.query("SELECT * FROM task_node_artifacts WHERE task_id = ?"
                + " ORDER BY created_at", this::mapArtifact, taskId);
    }

    public void insertArtifact(ArtifactRow row) {
        jdbc.update("INSERT INTO task_node_artifacts"
                + " (artifact_id, task_id, node_id, run_id, file_path, file_name,"
                + " artifact_type, description, created_by, created_at, version)"
                + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                row.artifactId(), row.taskId(), row.nodeId(), row.runId(),
                row.filePath(), row.fileName(), row.artifactType(),
                row.description(), row.createdBy(), epoch(row.createdAt()), row.version());
    }

    public int artifactCount(String taskId) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_node_artifacts WHERE task_id = ?",
                Integer.class, taskId);
        return value == null ? 0 : value;
    }

    public void deleteArtifactsForNodeExcept(String taskId, String nodeId, String keepRunId) {
        jdbc.update("DELETE FROM task_node_artifacts WHERE task_id = ? AND node_id = ?"
                + " AND run_id <> ?", taskId, nodeId, keepRunId);
    }

    // ---- 升级 ----

    public boolean hasOpenEscalation(String taskId, String reason) {
        Integer value = jdbc.queryForObject("SELECT COUNT(*) FROM task_escalations"
                + " WHERE task_id = ? AND reason = ? AND resolved_at IS NULL",
                Integer.class, taskId, reason);
        return value != null && value > 0;
    }

    public void addEscalation(String escalationId, String taskId, String reason,
                              String escalatedTo, Instant at, String runId,
                              String approvalId, int level) {
        jdbc.update("""
                INSERT INTO task_escalations (escalation_id, task_id, run_id, approval_id,
                    reason, escalated_to, escalated_at, level, resolved_by, resolved_at,
                    resolution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """, escalationId, taskId, runId, approvalId, reason, escalatedTo, epoch(at),
                level);
    }

    // ---- 变量 ----

    public void addVariable(String taskId, String key, String value, String actorId,
                            Instant now) {
        jdbc.update("""
                INSERT INTO task_variables (task_id, var_key, var_value, source, updated_by,
                    updated_at)
                VALUES (?, ?, ?, 'input', ?, ?)
                ON CONFLICT (task_id, var_key) DO UPDATE SET
                    var_value = excluded.var_value, updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """, taskId, key, value, actorId, epoch(now));
    }

    // ---- 审批 ----

    public ApprovalRow getApproval(String approvalId) {
        return jdbc.query("SELECT * FROM approval_items WHERE approval_id = ?",
                        this::mapApproval, approvalId)
                .stream().findFirst().orElse(null);
    }

    public List<ApprovalRow> listApprovals(String status) {
        if (status == null) {
            return jdbc.query("SELECT * FROM approval_items ORDER BY created_at",
                    this::mapApproval);
        }
        return jdbc.query("SELECT * FROM approval_items WHERE status = ? ORDER BY created_at",
                this::mapApproval, status);
    }

    public void saveApproval(ApprovalRow item) {
        jdbc.update("""
                UPDATE approval_items SET status = ?, resolved_by = ?, resolved_at = ?,
                    resolution_note = ?
                 WHERE approval_id = ?
                """, item.status(), item.resolvedBy(), epoch(item.resolvedAt()),
                item.resolutionNote(), item.approvalId());
    }

    public void addApproval(ApprovalRow item) {
        jdbc.update("""
                INSERT INTO approval_items (approval_id, task_id, node_id, title, tier, status,
                    requester_id, note, created_at, expires_at, resolved_by, resolved_at,
                    resolution_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, item.approvalId(), item.taskId(), item.nodeId(), item.title(), item.tier(),
                item.status(), item.requesterId(), item.note(), epoch(item.createdAt()),
                epoch(item.expiresAt()), item.resolvedBy(), epoch(item.resolvedAt()),
                item.resolutionNote());
    }

    public List<ApprovalRow> pendingApprovals(String taskId) {
        return jdbc.query("SELECT * FROM approval_items WHERE task_id = ? AND status = 'pending'",
                this::mapApproval, taskId);
    }

    public List<ApprovalRow> dueApprovals(Instant now) {
        return jdbc.query("SELECT * FROM approval_items WHERE status = 'pending'"
                + " AND expires_at <= ? ORDER BY expires_at", this::mapApproval, epoch(now));
    }

    // ---- 辅助 ----

    public String teamLeader(String teamId) {
        if (teamId == null) {
            return null;
        }
        List<String> values = jdbc.queryForList(
                "SELECT leader_employee_id FROM org_teams WHERE team_id = ?",
                String.class, teamId);
        return values.stream().filter(value -> value != null && !value.isBlank())
                .findFirst().orElse(null);
    }

    public String teamLeaderOfEmployee(String employeeId) {
        List<String> values = jdbc.queryForList("""
                SELECT t.leader_employee_id
                  FROM identity_employees e
                  JOIN org_teams t ON t.team_id = e.team_id
                 WHERE e.employee_id = ?
                """, String.class, employeeId);
        return values.stream().filter(value -> value != null && !value.isBlank())
                .findFirst().orElse(null);
    }

    public String employeeSeat(String employeeId) {
        List<String> values = jdbc.queryForList(
                "SELECT seat_id FROM identity_employees WHERE employee_id = ?",
                String.class, employeeId);
        return values.stream().filter(value -> value != null).findFirst().orElse("");
    }

    public io.github.hopewang123456.mailbus.identity.Employee employee(String employeeId) {
        return jdbc.query("""
                SELECT employee_id, display_name, account_type, status, team_id, position_id,
                       seat_id, data_scope
                  FROM identity_employees WHERE employee_id = ? AND deleted_at IS NULL
                """, (row, index) -> new io.github.hopewang123456.mailbus.identity.Employee(
                        row.getString("employee_id"), row.getString("display_name"),
                        row.getString("account_type"), row.getString("status"),
                        row.getString("team_id"), row.getString("position_id"),
                        row.getString("seat_id"), null, java.util.Set.of(),
                        row.getString("data_scope"), List.of(), null, false, null, null),
                employeeId).stream().findFirst().orElse(null);
    }

    private String taskFilters(String state, String ownerId, String workflowId,
                               String viewerId, List<Object> params) {
        List<String> clauses = new ArrayList<>();
        if (state != null) {
            clauses.add("state = ?");
            params.add(state);
        }
        if (ownerId != null) {
            clauses.add("owner_id = ?");
            params.add(ownerId);
        }
        if (workflowId != null) {
            clauses.add("workflow_id = ?");
            params.add(workflowId);
        }
        if (viewerId != null) {
            clauses.add("(owner_id = ? OR created_by = ? OR task_id IN"
                    + " (SELECT task_id FROM task_node_runs WHERE assigned_employee_id = ?))");
            params.add(viewerId);
            params.add(viewerId);
            params.add(viewerId);
        }
        return clauses.isEmpty() ? "" : " WHERE " + String.join(" AND ", clauses);
    }

    private TaskRow mapTask(ResultSet row, int index) throws SQLException {
        int version = row.getInt("workflow_version");
        Integer versionValue = row.wasNull() ? null : version;
        return new TaskRow(row.getString("task_id"), row.getString("title"),
                row.getString("state"), row.getString("workflow_id"), versionValue,
                row.getString("owner_id"), row.getString("created_by"),
                row.getString("termination_reason"), loopCounters(row.getString("loop_counters")),
                instant(row, "created_at"), instant(row, "updated_at"));
    }

    private NodeRow mapNode(ResultSet row, int index) throws SQLException {
        return new NodeRow(row.getString("task_id"), row.getString("node_id"),
                row.getString("name"), row.getInt("seq"), row.getString("state"),
                row.getString("current_run_id"), instant(row, "updated_at"));
    }

    private RunRow mapRun(ResultSet row, int index) throws SQLException {
        return new RunRow(row.getString("run_id"), row.getString("task_id"),
                row.getString("node_id"), row.getInt("attempt_no"), row.getInt("fanout_slot"),
                row.getString("assigned_employee_id"), row.getString("role_id"),
                row.getString("state"), row.getString("fanout_group"),
                row.getInt("short_fanout") == 1, row.getString("result"),
                row.getString("parent_run_id"), instant(row, "dispatched_at"),
                instant(row, "started_at"), instant(row, "completed_at"),
                instant(row, "deadline_at"), instant(row, "escalated_at"));
    }

    private ArtifactRow mapArtifact(ResultSet row, int index) throws SQLException {
        return new ArtifactRow(row.getString("artifact_id"), row.getString("task_id"),
                row.getString("node_id"), row.getString("run_id"), row.getString("file_path"),
                row.getString("file_name"), row.getString("artifact_type"),
                row.getString("description"), row.getString("created_by"),
                instant(row, "created_at"), row.getInt("version"));
    }

    private ApprovalRow mapApproval(ResultSet row, int index) throws SQLException {
        return new ApprovalRow(row.getString("approval_id"), row.getString("task_id"),
                row.getString("node_id"), row.getString("title"), row.getString("tier"),
                row.getString("status"), row.getString("requester_id"), row.getString("note"),
                instant(row, "created_at"), instant(row, "expires_at"),
                row.getString("resolved_by"), instant(row, "resolved_at"),
                row.getString("resolution_note"));
    }

    private Map<String, Integer> loopCounters(String raw) {
        if (raw == null || raw.isBlank()) {
            return Map.of();
        }
        try {
            Map<String, Integer> parsed = objectMapper.readValue(raw,
                    new TypeReference<LinkedHashMap<String, Integer>>() {
                    });
            return parsed == null ? Map.of() : parsed;
        } catch (Exception exception) {
            return Map.of();
        }
    }

    private String jsonLoop(Map<String, Integer> counters) {
        try {
            return objectMapper.writeValueAsString(counters == null ? Map.of() : counters);
        } catch (Exception exception) {
            return "{}";
        }
    }

    private Double epoch(Instant value) {
        return value == null ? null : (double) value.getEpochSecond();
    }

    private Instant instant(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }
}
