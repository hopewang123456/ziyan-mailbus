package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.identity.Employee;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 任务域用例：创建、认领、提交、取消、重跑、审批与升级清扫。 */
@Service
public class TaskService {

    private static final Set<String> OPEN_TASK_STATES = Set.of("pending", "running", "blocked");
    private static final Set<String> TERMINAL_TASK_STATES = Set.of("done", "cancelled", "failed");
    private static final Set<String> ACTIVE_NODE_STATES =
            Set.of("running", "dispatched", "waiting_human", "blocked");
    private static final Set<String> TERMINAL_NODE_STATES = Set.of("done", "failed", "skipped");
    private static final Set<String> APPROVAL_STATES = Set.of("pending", "approved",
            "rejected", "expired", "acknowledged", "withdrawn");
    private static final Set<String> TERMINATION_REASONS = Set.of("manual",
            "no_matching_branch", "auto_terminated", "approval_rejected");
    private static final Map<String, String> RUN_STATE_WIRE = Map.of(
            "pending", "pending", "dispatched", "running", "running", "running",
            "waiting_human", "pending", "done", "done", "failed", "failed",
            "skipped", "skipped");

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;
    private final WorkflowService workflows;
    private final TaskRepository repo;
    private final TaskGraph taskGraph;
    private final TaskStaff staff;
    private final TaskConditions conditions;
    private final ObjectMapper objectMapper;
    private final Path artifactsDir;

    public TaskService(JdbcTemplate jdbc, Ids ids, Outbox outbox, WorkflowService workflows,
                       TaskRepository repo, TaskGraph taskGraph, TaskStaff staff,
                       TaskConditions conditions, ObjectMapper objectMapper,
                       AppProperties props) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
        this.workflows = workflows;
        this.repo = repo;
        this.taskGraph = taskGraph;
        this.staff = staff;
        this.conditions = conditions;
        this.objectMapper = objectMapper;
        this.artifactsDir = props.artifactsDir();
    }

    // ---- 读 ----

    public TaskDtos.TaskListOut list(Actor actor, String state, String ownerId,
                                     String workflowId, int limit, int offset) {
        if (state != null && !state.isBlank() && !Set.of("pending", "running", "blocked",
                "done", "cancelled", "failed", "draft", "queued").contains(state)) {
            throw ApiException.unprocessable("unprocessable", "未知任务状态：" + state);
        }
        String viewer = "global".equals(actor.dataScope()) ? null : actor.employeeId();
        List<TaskRepository.TaskRow> rows = repo.listTasks(blankToNull(state),
                blankToNull(ownerId), blankToNull(workflowId), limit, offset, viewer);
        int total = repo.countTasks(blankToNull(state), blankToNull(ownerId),
                blankToNull(workflowId), viewer);
        List<TaskDtos.TaskSummaryOut> items = new ArrayList<>();
        for (TaskRepository.TaskRow row : rows) {
            items.add(summary(actor, row));
        }
        return new TaskDtos.TaskListOut(items, total, limit, offset);
    }

    public TaskDtos.TaskDetailOut get(Actor actor, String taskId) {
        TaskRepository.TaskRow task = load(taskId);
        ensureVisible(actor, task);
        return detail(taskId);
    }

    public TaskDtos.TaskTraceOut trace(Actor actor, String taskId) {
        TaskDtos.TaskDetailOut detail = get(actor, taskId);
        List<TaskDtos.TaskTraceEventOut> events = new ArrayList<>();
        events.add(new TaskDtos.TaskTraceEventOut(detail.createdAt(), "task.created",
                null, null, null, Map.of("title", detail.title(), "state", detail.state())));
        for (TaskDtos.TaskRunOut run : detail.runs()) {
            addRunTrace(events, "run.dispatched", run.dispatchedAt(), run);
            addRunTrace(events, "run.started", run.startedAt(), run);
            addRunTrace(events, "run.completed", run.completedAt(), run);
        }
        events.sort(Comparator.comparing(TaskDtos.TaskTraceEventOut::at,
                Comparator.nullsLast(Comparator.naturalOrder())));
        return new TaskDtos.TaskTraceOut(detail.taskId(), events);
    }

    public TaskDtos.TaskCountersOut counters(Actor actor) {
        Employee employee = repo.employee(actor.employeeId());
        int claimable = 0;
        for (TaskRepository.TaskRow task : repo.listTasks(null, null, null, null, null, null)) {
            if (!OPEN_TASK_STATES.contains(task.state())) {
                continue;
            }
            for (TaskRepository.RunRow run : repo.runsByTask(task.taskId())) {
                if ("waiting_human".equals(run.state()) && run.assignedEmployeeId() == null
                        && staff.canClaim(employee, graphNode(task, run.nodeId()))) {
                    claimable++;
                }
            }
        }
        int mine = repo.countTasks(null, actor.employeeId(), null, null);
        int approvals = visibleApprovals(actor, repo.listApprovals("pending")).size();
        return new TaskDtos.TaskCountersOut(claimable, mine, approvals);
    }

    /** 大屏公开投影：不做可见性判定，调用方负责鉴权。 */
    public List<TaskDtos.TaskDetailOut> listByOwner(String ownerId) {
        return repo.listTasks(null, ownerId, null, null, null, null).stream()
                .map(task -> detail(task.taskId())).toList();
    }

    public List<TaskDtos.TaskDetailOut> allInternal() {
        return repo.listTasks(null, null, null, null, null, null).stream()
                .map(task -> detail(task.taskId())).toList();
    }

    public TaskDtos.TaskDetailOut getInternal(String taskId) {
        return detail(load(taskId).taskId());
    }

    // ---- 创建 ----

    @Transactional
    public TaskDtos.TaskDetailOut create(Actor actor, TaskDtos.TaskCreateIn input) {
        String ownerId = input.ownerId() == null || input.ownerId().isBlank()
                ? actor.employeeId() : input.ownerId();
        Authz.ensureAllowed(actor, Authz.TASK_CREATE, Authz.Resource.owned("task", ownerId));
        if (!ownerId.equals(actor.employeeId())) {
            Authz.ensureAllowed(actor, Authz.TASK_DISPATCH,
                    Authz.Resource.owned("task", ownerId));
        }
        Instant now = Instant.now();
        String taskId = ids.next("task");
        TaskGraph.Index graph = null;
        TaskRepository.TaskRow task;
        if (input.workflowId() != null && !input.workflowId().isBlank()) {
            WorkflowDtos.WorkflowOut definition = workflows.loadDefinition(input.workflowId());
            Integer number = definition.publishedVersion();
            if (number == null) {
                throw ApiException.conflict("version_not_published", "流程尚未发布版本");
            }
            WorkflowDtos.VersionOut version = workflows.loadVersion(input.workflowId(), number);
            if (!"published".equals(version.state())) {
                throw ApiException.conflict("version_not_published",
                        "只能从已发布版本创建任务");
            }
            graph = taskGraph.load(input.workflowId(), number);
            if (graph.nodes().isEmpty()) {
                throw ApiException.unprocessable("unprocessable", "流程没有可执行节点");
            }
            task = new TaskRepository.TaskRow(taskId, input.title(), "running",
                    input.workflowId(), number, ownerId, actor.employeeId(), null, Map.of(),
                    now, now);
            repo.insertTask(task);
            for (TaskGraph.GraphNode node : graph.nodes()) {
                repo.saveNode(new TaskRepository.NodeRow(taskId, node.nodeId(), node.name(),
                        node.seq(), "pending", null, now));
            }
        } else {
            task = new TaskRepository.TaskRow(taskId, input.title(), "running", null, null,
                    ownerId, actor.employeeId(), null, Map.of(), now, now);
            repo.insertTask(task);
            repo.saveNode(new TaskRepository.NodeRow(taskId, TaskFlow.FREE_NODE_ID,
                    input.title(), 0, "pending", null, now));
        }
        if (input.variables() != null) {
            input.variables().forEach((key, value) ->
                    repo.addVariable(taskId, key, value, actor.employeeId(), now));
        }
        TaskFlow flow = flow(task, graph);
        if (graph != null) {
            flow.startGraph();
        } else {
            flow.startFree(ownerId);
        }
        publish(taskId);
        return detail(taskId);
    }

    // ---- 认领与提交 ----

    @Transactional
    public TaskDtos.TaskDetailOut claim(Actor actor, String taskId, String nodeId) {
        TaskRepository.TaskRow task = load(taskId);
        ensureOpen(task);
        TaskRepository.RunRow run = claimableRun(taskId, nodeId);
        Employee employee = repo.employee(actor.employeeId());
        if (!actor.has(Authz.ALL)
                && (employee == null || !staff.canClaim(employee, graphNode(task, nodeId)))) {
            throw ApiException.forbidden("不属于该节点的候选岗位");
        }
        Instant now = Instant.now();
        if (!repo.claim(run.runId(), actor.employeeId(), now)) {
            throw ApiException.invalid("节点已被其他成员认领");
        }
        TaskRepository.NodeRow node = repo.getNode(taskId, nodeId);
        if (node != null) {
            repo.saveNode(node.withState("running", run.runId(), now));
        }
        repo.saveTask(task.withOwner(actor.employeeId(), now).withState("running", now));
        publish(taskId);
        return detail(taskId);
    }

    @Transactional
    public TaskDtos.TaskDetailOut submit(Actor actor, String taskId, String nodeId,
                                         TaskDtos.ResultIn input) {
        TaskRepository.TaskRow task = load(taskId);
        ensureOpen(task);
        TaskRepository.RunRow run = runForSubmit(taskId, nodeId, input.attemptNo());
        if (!actor.has(Authz.ALL) && run.assignedEmployeeId() != null
                && !run.assignedEmployeeId().equals(actor.employeeId())) {
            throw ApiException.forbidden("只有当前执行人可以提交结果");
        }
        if (input.artifactIds() != null) {
            for (String artifactId : input.artifactIds()) {
                TaskRepository.ArtifactRow artifact = repo.getArtifact(artifactId);
                if (artifact == null || !artifact.taskId().equals(taskId)) {
                    throw ApiException.unprocessable("unprocessable", "产物不存在：" + artifactId);
                }
            }
        }
        if ("done".equals(run.state()) || "failed".equals(run.state())) {
            if (Objects.equals(run.result(), input.result())) {
                return detail(taskId);
            }
            throw ApiException.invalid("该执行实例已提交过结果");
        }
        Instant now = Instant.now();
        String assigned = run.assignedEmployeeId() == null
                ? actor.employeeId() : run.assignedEmployeeId();
        TaskRepository.RunRow running = run.withSubmission(assigned, "running",
                run.startedAt() == null ? now : run.startedAt(), run.completedAt(), run.result());
        repo.saveRun(running);
        TaskFlow flow = flow(task, graphOf(task));
        if (conditions.isFailedResult(input.result())) {
            flow.fail(running, input.result());
        } else {
            flow.complete(running, input.result());
        }
        repo.saveTask(flow.task().withOwner(actor.employeeId(), now));
        publish(taskId);
        return detail(taskId);
    }

    // ---- 取消与重跑 ----

    @Transactional
    public TaskDtos.TaskDetailOut cancel(Actor actor, String taskId, String reason) {
        String parsed = reason == null || reason.isBlank() ? "manual" : reason;
        if (!TERMINATION_REASONS.contains(parsed)) {
            throw ApiException.unprocessable("unprocessable", "未知终止原因：" + reason);
        }
        TaskRepository.TaskRow task = load(taskId);
        ensureOperator(actor, task);
        ensureOpen(task);
        flow(task, graphOf(task)).terminate(parsed);
        publish(taskId);
        return detail(taskId);
    }

    @Transactional
    public TaskDtos.TaskDetailOut rerunJoin(Actor actor, String taskId, String nodeId,
                                            TaskDtos.RerunJoinIn input) {
        TaskRepository.TaskRow task = load(taskId);
        ensureOperator(actor, task);
        ensureOpen(task);
        TaskGraph.Index graph = graphOf(task);
        TaskGraph.GraphNode node = graph == null ? null : graph.node(nodeId);
        if (node == null || !"parallel_join".equals(node.nodeType())) {
            throw ApiException.unprocessable("unprocessable", "只有汇聚节点可以重跑");
        }
        List<TaskRepository.RunRow> runs = repo.runsByNode(taskId, nodeId);
        if (runs.stream().anyMatch(item -> TaskFlow.OPEN_RUN_STATES.contains(item.state()))) {
            throw ApiException.invalid("汇聚仍在执行中");
        }
        TaskFlow flow = flow(task, graph);
        if (flow.joinState(nodeId).ready()) {
            throw ApiException.invalid("汇聚已满足推进条件，无需重跑");
        }
        String scope = input.scope() == null ? "join" : input.scope();
        List<String> missing = flow.forceJoin(nodeId, input.fanoutGroup(), scope);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("task_id", taskId);
        detail.put("node_id", nodeId);
        detail.put("attempt_no", flow.lastAttempt());
        detail.put("fanout_group", input.fanoutGroup());
        detail.put("scope", scope);
        detail.put("missing", missing);
        recordAudit(actor.employeeId(), "task.join_rerun", "task:" + taskId, detail);
        publish(taskId);
        return detail(taskId);
    }

    // ---- 审批 ----

    public List<TaskRepository.ApprovalRow> listApprovals(Actor actor, String state,
                                                          int limit, int offset) {
        if (state != null && !state.isBlank() && !APPROVAL_STATES.contains(state)) {
            throw ApiException.invalid("未知审批状态：" + state);
        }
        List<TaskRepository.ApprovalRow> visible =
                visibleApprovals(actor, repo.listApprovals(blankToNull(state)));
        int from = Math.min(offset, visible.size());
        int to = Math.min(from + limit, visible.size());
        return visible.subList(from, to);
    }

    public int countApprovals(Actor actor, String state) {
        return visibleApprovals(actor, repo.listApprovals(blankToNull(state))).size();
    }

    @Transactional
    public TaskRepository.ApprovalRow resolveApproval(Actor actor, String approvalId,
                                                      String decision, String comment) {
        Authz.require(actor, Authz.HITL_RESOLVE);
        if ("rejected".equals(decision) && (comment == null || comment.strip().isEmpty())) {
            throw ApiException.unprocessable("unprocessable", "驳回必须填写意见");
        }
        Instant now = Instant.now();
        TaskRepository.ApprovalRow item = repo.getApproval(approvalId);
        if (item == null) {
            throw ApiException.notFound("审批不存在");
        }
        if (!"pending".equals(item.status())) {
            throw ApiException.invalid("审批已处理");
        }
        TaskRepository.TaskRow task = load(item.taskId());
        TaskGraph.Index graph = graphOf(task);
        TaskGraph.GraphNode node = graph != null && item.nodeId() != null
                ? graph.node(item.nodeId()) : null;
        if (node == null || !"final_approval".equals(node.nodeType())) {
            return resolveLegacy(actor, item, decision, comment, now);
        }
        ensureApprover(actor, node);
        boolean approved = "approved".equals(decision);
        repo.saveApproval(item.resolved(approved ? "approved" : "rejected",
                actor.employeeId(), comment, now));
        for (TaskRepository.RunRow run : repo.runsByNode(task.taskId(), item.nodeId())) {
            if (TaskFlow.OPEN_RUN_STATES.contains(run.state())) {
                repo.saveRun(run.withState(approved ? "done" : "failed", now));
            }
        }
        TaskFlow flow = flow(task, graph);
        if (approved) {
            flow.approve(item.nodeId());
        } else {
            flow.reject(item.nodeId());
        }
        repo.saveTask(flow.task());
        outbox.enqueue(approved ? "approval.approved" : "approval.rejected",
                Map.of("approval_id", approvalId, "task_id", item.taskId(),
                        "resolver_id", actor.employeeId()));
        publish(item.taskId());
        return repo.getApproval(approvalId);
    }

    private TaskRepository.ApprovalRow resolveLegacy(Actor actor, TaskRepository.ApprovalRow item,
                                                     String decision, String comment,
                                                     Instant now) {
        boolean approved = "approved".equals(decision);
        if ("acknowledged".equals(item.status())) {
            throw ApiException.invalid("信息档审批无需裁决");
        }
        if ("expired".equals(item.status())) {
            throw ApiException.invalid("审批已超时");
        }
        repo.saveApproval(item.resolved(approved ? "approved" : "rejected",
                actor.employeeId(), comment, now));
        if ("blocking".equals(item.tier())) {
            if (approved) {
                resume(item.taskId());
            } else {
                fail(item.taskId(), "approval_rejected");
            }
        }
        outbox.enqueue(approved ? "approval.approved" : "approval.rejected",
                Map.of("approval_id", item.approvalId(), "task_id", item.taskId(),
                        "resolver_id", actor.employeeId()));
        publish(item.taskId());
        return repo.getApproval(item.approvalId());
    }

    // ---- 产物 ----

    public record DownloadFile(Path path, String fileName) {
    }

    public DownloadFile download(Actor actor, String artifactId) {
        TaskRepository.ArtifactRow artifact = repo.getArtifact(artifactId);
        if (artifact == null) {
            throw ApiException.notFound("产物不存在");
        }
        TaskRepository.TaskRow task = load(artifact.taskId());
        if (!actor.has(Authz.ARTIFACT_READ_ALL)) {
            ensureVisible(actor, task);
        }
        Path path = Path.of(artifact.filePath());
        if (!Files.isRegularFile(path)) {
            throw ApiException.gone("resource_gone", "产物文件已失效");
        }
        return new DownloadFile(path, artifact.fileName());
    }

    @Transactional
    public TaskDtos.ArtifactOut upload(Actor actor, String taskId, String nodeId,
                                       String fileName, byte[] bytes, String description) {
        if (bytes == null || bytes.length == 0) {
            throw ApiException.unprocessable("unprocessable", "产物文件为空");
        }
        TaskRepository.TaskRow task = load(taskId);
        ensureVisible(actor, task);
        ensureOpen(task);
        boolean nodeExists = repo.nodes(taskId).stream()
                .anyMatch(node -> node.nodeId().equals(nodeId));
        if (!nodeExists) {
            throw ApiException.unprocessable("unprocessable", "节点不属于该任务");
        }
        List<TaskRepository.RunRow> nodeRuns = repo.runsByTask(taskId).stream()
                .filter(run -> run.nodeId().equals(nodeId)).toList();
        if (nodeRuns.isEmpty()) {
            throw ApiException.invalid("节点尚未派发执行实例");
        }
        TaskRepository.RunRow run = nodeRuns.stream()
                .max(Comparator.comparingInt(TaskRepository.RunRow::attemptNo))
                .orElseThrow();
        if (!actor.has(Authz.ALL)
                && !actor.employeeId().equals(task.ownerId())
                && !actor.employeeId().equals(task.createdBy())
                && run.assignedEmployeeId() != null
                && !run.assignedEmployeeId().equals(actor.employeeId())) {
            throw ApiException.forbidden("只有当前执行人可以上传产物");
        }
        String artifactId = ids.next("artifact");
        String safe = Path.of(fileName == null ? "artifact" : fileName).getFileName().toString();
        if (safe == null || safe.isBlank()) {
            safe = "artifact";
        }
        Path dest = artifactsDir.resolve(taskId).resolve(artifactId + "_" + safe);
        try {
            Files.createDirectories(dest.getParent());
            Files.write(dest, bytes);
        } catch (IOException e) {
            throw ApiException.unprocessable("unprocessable", "产物写入失败");
        }
        Instant now = Instant.now();
        TaskRepository.ArtifactRow row = new TaskRepository.ArtifactRow(
                artifactId, taskId, nodeId, run.runId(), dest.toString(), safe, null,
                description == null || description.isBlank() ? null : description,
                actor.employeeId(), now, 1);
        repo.insertArtifact(row);
        outbox.enqueue("task.artifact_upload", Map.of(
                "task_id", taskId, "node_id", nodeId, "run_id", run.runId(),
                "artifact_id", artifactId, "file_name", safe));
        return artifactOut(row);
    }

    // ---- 超时清扫 ----

    @Transactional
    public int sweepTimeouts() {
        Instant now = Instant.now();
        int count = 0;
        for (TaskRepository.RunRow run : repo.overdueRuns(now, 500)) {
            count += sweepRun(run, now);
        }
        for (TaskRepository.ApprovalRow item : repo.dueApprovals(now)) {
            repo.saveApproval(item.resolved("expired", item.resolvedBy(), null, now));
            TaskRepository.TaskRow task = repo.getTask(item.taskId());
            if (task != null) {
                flow(task, graphOf(task)).escalate("approval_timeout", item.nodeId(),
                        null, item.approvalId(), 1);
            }
            count++;
        }
        return count;
    }

    private int sweepRun(TaskRepository.RunRow run, Instant now) {
        TaskRepository.TaskRow task = repo.getTask(run.taskId());
        if (task == null || "done".equals(task.state()) || "cancelled".equals(task.state())) {
            return 0;
        }
        TaskFlow flow = flow(task, graphOf(task));
        if (run.escalatedAt() == null) {
            repo.saveRun(run.withEscalatedAt(now));
            flow.escalate("work_timeout", run.nodeId(), run.runId(), null, 1);
        } else if (Duration.between(run.escalatedAt(), now).getSeconds()
                > TaskFlow.ESCALATION_TERMINATE_SECONDS) {
            flow.escalate("work_timeout", run.nodeId(), run.runId(), null, 2);
            flow.terminate("auto_terminated");
        }
        return 1;
    }

    @Transactional
    public void hold(String taskId, String reason) {
        TaskRepository.TaskRow task = load(taskId);
        if (TERMINAL_TASK_STATES.contains(task.state())) {
            throw ApiException.conflict("invalid_transition", "任务已结束，不能阻塞");
        }
        Instant now = Instant.now();
        repo.saveTask(task.withState("blocked", now));
        repo.nodes(taskId).stream()
                .filter(node -> Set.of("dispatched", "running").contains(node.state()))
                .forEach(node -> repo.saveNode(node.withState("blocked",
                        node.currentRunId(), now)));
        outbox.enqueue("task.blocked", Map.of("task_id", taskId, "reason", reason));
    }

    @Transactional
    public void resume(String taskId) {
        TaskRepository.TaskRow task = load(taskId);
        if (!"blocked".equals(task.state())) {
            throw ApiException.conflict("invalid_transition", "只有阻塞中的任务可以恢复");
        }
        Instant now = Instant.now();
        repo.saveTask(task.withState("running", now));
        repo.nodes(taskId).stream()
                .filter(node -> "blocked".equals(node.state()))
                .forEach(node -> repo.saveNode(node.withState("running",
                        node.currentRunId(), now)));
        outbox.enqueue("task.resumed", Map.of("task_id", taskId));
    }

    @Transactional
    public void fail(String taskId, String reason) {
        TaskRepository.TaskRow task = load(taskId);
        if ("failed".equals(task.state())) {
            return;
        }
        if (TERMINAL_TASK_STATES.contains(task.state())) {
            throw ApiException.conflict("invalid_transition", "任务已结束，不能标记失败");
        }
        Instant now = Instant.now();
        repo.saveTask(task.withState("failed", now));
        repo.nodes(taskId).stream()
                .filter(node -> !TERMINAL_NODE_STATES.contains(node.state()))
                .forEach(node -> repo.saveNode(node.withState("failed",
                        node.currentRunId(), now)));
        outbox.enqueue("task.failed", Map.of("task_id", taskId, "reason", reason));
    }

    // ---- 投影 ----

    public TaskDtos.TaskDetailOut detail(String taskId) {
        TaskRepository.TaskRow task = load(taskId);
        List<TaskRepository.RunRow> runs = repo.runsByTask(taskId);
        List<TaskDtos.TaskRunOut> runOuts = runs.stream().map(this::runOut).toList();
        List<TaskDtos.TaskNodeOut> nodes = new ArrayList<>();
        for (TaskRepository.NodeRow node : repo.nodes(taskId)) {
            List<TaskDtos.TaskRunOut> nodeRuns = runOuts.stream()
                    .filter(run -> run.nodeId().equals(node.nodeId())).toList();
            nodes.add(new TaskDtos.TaskNodeOut(node.nodeId(), node.name(), node.seq(),
                    node.state(), node.currentRunId(), nodeRuns));
        }
        return new TaskDtos.TaskDetailOut(task.taskId(), task.title(), task.state(),
                task.ownerId(), task.createdBy(), task.workflowId(), task.workflowVersion(),
                task.terminationReason(), task.createdAt(), task.updatedAt(), nodes, runOuts,
                repo.listArtifacts(taskId).stream().map(this::artifactOut).toList());
    }

    private TaskDtos.ArtifactOut artifactOut(TaskRepository.ArtifactRow row) {
        Long size = null;
        try {
            size = Files.size(Path.of(row.filePath()));
        } catch (IOException ignored) {
            // 文件缺失时 size 留空，下载时会返回 410
        }
        return new TaskDtos.ArtifactOut(row.artifactId(), row.taskId(), row.nodeId(),
                row.runId(), row.fileName(), row.artifactType(), row.description(),
                size, row.createdBy(), row.createdAt());
    }

    private TaskDtos.TaskRunOut runOut(TaskRepository.RunRow run) {
        return new TaskDtos.TaskRunOut(run.runId(), run.nodeId(), run.attemptNo(),
                run.fanoutSlot(), RUN_STATE_WIRE.getOrDefault(run.state(), run.state()),
                run.assignedEmployeeId(), run.fanoutGroup(), run.dispatchedAt(),
                run.startedAt(), run.completedAt(), run.result());
    }

    private void addRunTrace(List<TaskDtos.TaskTraceEventOut> events, String kind, Instant at,
                             TaskDtos.TaskRunOut run) {
        if (at == null) {
            return;
        }
        events.add(new TaskDtos.TaskTraceEventOut(at, kind, run.nodeId(), run.runId(),
                run.attemptNo(), Map.of("state", run.state())));
    }

    private TaskDtos.TaskSummaryOut summary(Actor actor, TaskRepository.TaskRow task) {
        List<TaskRepository.NodeRow> nodes = repo.nodes(task.taskId());
        List<TaskRepository.RunRow> runs = repo.runsByTask(task.taskId());
        Employee employee = repo.employee(actor.employeeId());
        Set<String> claimableNodes = new java.util.HashSet<>();
        for (TaskRepository.RunRow run : runs) {
            if ("waiting_human".equals(run.state()) && run.assignedEmployeeId() == null
                    && staff.canClaim(employee, graphNode(task, run.nodeId()))) {
                claimableNodes.add(run.nodeId());
            }
        }
        TaskRepository.NodeRow current = currentNode(nodes);
        boolean claimable = runs.stream().anyMatch(run ->
                "waiting_human".equals(run.state()) && run.assignedEmployeeId() == null
                        && claimableNodes.contains(run.nodeId()));
        int done = (int) nodes.stream().filter(node -> "done".equals(node.state())).count();
        return new TaskDtos.TaskSummaryOut(task.taskId(), task.title(), task.state(),
                task.ownerId(), task.workflowId(), task.workflowVersion(), task.createdAt(),
                task.updatedAt(), current == null ? null : current.name(), done, nodes.size(),
                claimable);
    }

    private TaskRepository.NodeRow currentNode(List<TaskRepository.NodeRow> nodes) {
        for (String state : List.of("running", "dispatched", "waiting_human", "blocked")) {
            for (TaskRepository.NodeRow node : nodes) {
                if (state.equals(node.state())) {
                    return node;
                }
            }
        }
        for (TaskRepository.NodeRow node : nodes) {
            if ("pending".equals(node.state())) {
                return node;
            }
        }
        return nodes.isEmpty() ? null : nodes.get(nodes.size() - 1);
    }

    private void publish(String taskId) {
        TaskRepository.TaskRow task = repo.getTask(taskId);
        if (task == null) {
            return;
        }
        List<TaskRepository.NodeRow> nodes = repo.nodes(taskId);
        TaskRepository.NodeRow current = currentNode(nodes);
        int done = (int) nodes.stream()
                .filter(node -> Set.of("done", "skipped").contains(node.state())).count();
        String seat = task.ownerId() == null ? "" : repo.employeeSeat(task.ownerId());
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", taskId);
        payload.put("seat_id", seat == null ? "" : seat);
        payload.put("title", task.title());
        payload.put("state", task.state());
        payload.put("current_node", current == null ? "" : current.name());
        payload.put("node_state", current == null ? "" : current.state());
        payload.put("progress_done", done);
        payload.put("progress_total", nodes.size());
        payload.put("updated_at", task.updatedAt() == null ? null : task.updatedAt().toString());
        outbox.enqueue("task.updated", payload);
    }

    // ---- 内部 ----

    private TaskRepository.TaskRow load(String taskId) {
        TaskRepository.TaskRow task = repo.getTask(taskId);
        if (task == null) {
            throw ApiException.notFound("任务不存在");
        }
        return task;
    }

    private TaskGraph.Index graphOf(TaskRepository.TaskRow task) {
        if (task.workflowId() == null || task.workflowVersion() == null) {
            return null;
        }
        return taskGraph.load(task.workflowId(), task.workflowVersion());
    }

    private TaskGraph.GraphNode graphNode(TaskRepository.TaskRow task, String nodeId) {
        if ("free".equals(nodeId)) {
            return null;
        }
        TaskGraph.Index graph = graphOf(task);
        return graph == null ? null : graph.node(nodeId);
    }

    private TaskFlow flow(TaskRepository.TaskRow task, TaskGraph.Index graph) {
        return new TaskFlow(repo, graph, task, repo.nodes(task.taskId()), ids, staff,
                conditions, objectMapper);
    }

    private void ensureOpen(TaskRepository.TaskRow task) {
        if (Set.of("done", "cancelled").contains(task.state())) {
            throw ApiException.invalid("任务已结束");
        }
    }

    private void ensureOperator(Actor actor, TaskRepository.TaskRow task) {
        if (actor.has(Authz.ALL) || actor.employeeId().equals(task.createdBy())) {
            return;
        }
        throw ApiException.forbidden("只有发起人或超管可以执行该操作");
    }

    private void ensureVisible(Actor actor, TaskRepository.TaskRow task) {
        if ("global".equals(actor.dataScope())) {
            return;
        }
        if (actor.employeeId().equals(task.ownerId())
                || actor.employeeId().equals(task.createdBy())) {
            return;
        }
        List<TaskRepository.RunRow> runs = repo.runsByTask(task.taskId());
        if (runs.stream().anyMatch(run ->
                actor.employeeId().equals(run.assignedEmployeeId()))) {
            return;
        }
        if ("team".equals(actor.dataScope()) && actor.teamId() != null
                && task.ownerId() != null) {
            Employee owner = repo.employee(task.ownerId());
            if (owner != null && actor.teamId().equals(owner.teamId())) {
                return;
            }
        }
        throw ApiException.forbidden("无权查看该任务");
    }

    private void ensureApprover(Actor actor, TaskGraph.GraphNode node) {
        if (actor.has(Authz.ALL)) {
            return;
        }
        Object narrowed = node.config().get("assignee_id");
        if (narrowed != null && !narrowed.toString().equals(actor.employeeId())) {
            throw ApiException.forbidden("你不是该终验的指定审批人");
        }
        if (narrowed != null) {
            return;
        }
        Employee employee = repo.employee(actor.employeeId());
        if (employee == null || !staff.canClaim(employee, node)) {
            throw ApiException.forbidden("你不是该终验节点的审批人");
        }
    }

    private TaskRepository.RunRow claimableRun(String taskId, String nodeId) {
        List<TaskRepository.RunRow> runs = repo.runsByNode(taskId, nodeId);
        List<TaskRepository.RunRow> sorted = new ArrayList<>(runs);
        sorted.sort((left, right) -> Integer.compare(right.attemptNo(), left.attemptNo()));
        for (TaskRepository.RunRow run : sorted) {
            if ("waiting_human".equals(run.state()) && run.assignedEmployeeId() == null) {
                return run;
            }
        }
        throw ApiException.invalid("节点当前没有可认领的待办");
    }

    private TaskRepository.RunRow runForSubmit(String taskId, String nodeId, int attemptNo) {
        List<TaskRepository.RunRow> runs = repo.runsByNode(taskId, nodeId).stream()
                .filter(run -> run.attemptNo() == attemptNo).toList();
        if (runs.isEmpty()) {
            int latest = repo.maxAttempt(taskId, nodeId);
            throw ApiException.invalid(latest > 0
                    ? "执行实例已过期：当前 attempt_no=" + latest : "节点尚未派发");
        }
        return runs.stream()
                .filter(run -> TaskFlow.OPEN_RUN_STATES.contains(run.state()))
                .findFirst().orElse(runs.get(0));
    }

    private List<TaskRepository.ApprovalRow> visibleApprovals(
            Actor actor, List<TaskRepository.ApprovalRow> items) {
        if ("global".equals(actor.dataScope())) {
            return items;
        }
        List<TaskRepository.ApprovalRow> visible = new ArrayList<>();
        for (TaskRepository.ApprovalRow item : items) {
            if (actor.employeeId().equals(item.requesterId())) {
                visible.add(item);
                continue;
            }
            TaskRepository.TaskRow task = repo.getTask(item.taskId());
            if (task == null) {
                continue;
            }
            if (actor.employeeId().equals(task.ownerId())
                    || actor.employeeId().equals(task.createdBy())) {
                visible.add(item);
                continue;
            }
            if ("team".equals(actor.dataScope()) && actor.teamId() != null
                    && task.ownerId() != null) {
                Employee owner = repo.employee(task.ownerId());
                if (owner != null && actor.teamId().equals(owner.teamId())) {
                    visible.add(item);
                }
            }
        }
        return visible;
    }

    private void recordAudit(String actorId, String action, String resource,
                             Map<String, Object> detail) {
        try {
            jdbc.update("""
                    INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """, actorId, action, resource, objectMapper.writeValueAsString(detail),
                    Instant.now().getEpochSecond());
        } catch (Exception exception) {
            throw new IllegalStateException("审计写入失败", exception);
        }
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
}
