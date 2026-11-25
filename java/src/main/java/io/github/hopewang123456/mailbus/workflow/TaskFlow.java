package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.common.Ids;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 任务推进：派发、汇聚、重试、循环保护与升级。唯一推进入口。 */
public class TaskFlow {

    public static final String FREE_NODE_ID = "free";
    public static final Set<String> OPEN_RUN_STATES =
            Set.of("pending", "dispatched", "running", "waiting_human");
    public static final Set<String> TERMINAL_RUN_STATES =
            Set.of("done", "failed", "skipped");
    public static final Set<String> TERMINAL_NODE_STATES =
            Set.of("done", "failed", "skipped");
    public static final long DEFAULT_WORK_TIMEOUT_SECONDS = 72L * 3600;
    public static final long DEFAULT_APPROVAL_TIMEOUT_MINUTES = 24L * 60;
    public static final long ESCALATION_TERMINATE_SECONDS = 72L * 3600;

    private final TaskRepository repo;
    private final TaskGraph.Index graph;
    private final Ids ids;
    private final TaskStaff staff;
    private final TaskConditions conditions;
    private final ObjectMapper objectMapper;

    private TaskRepository.TaskRow task;
    private final Map<String, TaskRepository.NodeRow> nodes = new LinkedHashMap<>();
    private boolean blocked;
    private int lastAttempt;

    public TaskFlow(TaskRepository repo, TaskGraph.Index graph, TaskRepository.TaskRow task,
                    List<TaskRepository.NodeRow> nodeRows, Ids ids, TaskStaff staff,
                    TaskConditions conditions, ObjectMapper objectMapper) {
        this.repo = repo;
        this.graph = graph;
        this.task = task;
        this.ids = ids;
        this.staff = staff;
        this.conditions = conditions;
        this.objectMapper = objectMapper;
        for (TaskRepository.NodeRow node : nodeRows) {
            nodes.put(node.nodeId(), node);
        }
        this.blocked = "blocked".equals(task.state());
    }

    public TaskRepository.TaskRow task() {
        return task;
    }

    public int lastAttempt() {
        return lastAttempt;
    }

    // ---- 入口 ----

    public void startGraph() {
        List<String> starts = new ArrayList<>();
        for (String nodeId : graph.startNodes()) {
            TaskGraph.GraphNode node = graph.node(nodeId);
            if (node != null && "start".equals(node.nodeType())) {
                starts.add(nodeId);
            }
        }
        if (starts.isEmpty()) {
            starts = graph.startNodes();
        }
        for (String nodeId : starts) {
            dispatch(nodeId, 0, null);
        }
        settle();
    }

    public TaskRepository.RunRow startFree(String ownerId) {
        Instant now = Instant.now();
        saveNode(new TaskRepository.NodeRow(task.taskId(), FREE_NODE_ID, task.title(), 0,
                "running", null, now));
        TaskRepository.RunRow run = new TaskRepository.RunRow(ids.next("run"), task.taskId(),
                FREE_NODE_ID, 1, 0, ownerId, null, "dispatched", null, false, null, null,
                now, null, null, now.plusSeconds(DEFAULT_WORK_TIMEOUT_SECONDS), null);
        repo.addRun(run);
        saveNode(nodes.get(FREE_NODE_ID).withState("running", run.runId(), now));
        return run;
    }

    // ---- 派发 ----

    public void dispatch(String nodeId, int slot, String parentRunId) {
        TaskRepository.NodeRow node = nodes.get(nodeId);
        TaskGraph.GraphNode wf = wf(nodeId);
        if (node == null || wf == null) {
            return;
        }
        if ("running".equals(node.state()) && node.currentRunId() != null) {
            return;
        }
        if ("done".equals(node.state()) && forced(nodeId)) {
            return;
        }
        if ("done".equals(node.state()) && enterLoop(node, wf)) {
            return;
        }
        if ("start".equals(wf.nodeType()) || "condition".equals(wf.nodeType())) {
            saveNode(node.withState("done", null, Instant.now()));
            advance(nodeId);
            return;
        }
        if ("parallel_join".equals(wf.nodeType())) {
            join(nodeId);
            return;
        }
        if ("final_approval".equals(wf.nodeType())) {
            human(node, wf, true);
            return;
        }
        if ("human".equals(wf.nodeType())) {
            human(node, wf, false);
            return;
        }
        dispatchAgent(node, wf, parentRunId);
    }

    private void human(TaskRepository.NodeRow node, TaskGraph.GraphNode wf, boolean approval) {
        Instant now = Instant.now();
        int attempt = repo.maxAttempt(task.taskId(), node.nodeId()) + 1;
        int fanout = approval ? 1 : fanout(wf);
        String group = fanout > 1 ? task.taskId() + ":" + node.nodeId() + ":" + attempt : null;
        List<Integer> slots = new ArrayList<>();
        if (fanout > 1) {
            for (int index = 1; index <= fanout; index++) {
                slots.add(index);
            }
        } else {
            slots.add(0);
        }
        TaskRepository.RunRow latest = null;
        for (int slot : slots) {
            latest = new TaskRepository.RunRow(ids.next("run"), task.taskId(), node.nodeId(),
                    attempt, slot, null, null, "waiting_human", group, false, null, null,
                    now, null, null, now.plusSeconds(timeout(wf)), null);
            repo.addRun(latest);
        }
        saveNode(node.withState("running", latest == null ? null : latest.runId(), now));
        markRunning();
        if (approval) {
            Instant expires = now.plusSeconds(DEFAULT_APPROVAL_TIMEOUT_MINUTES * 60);
            repo.addApproval(new TaskRepository.ApprovalRow(ids.next("appr"), task.taskId(),
                    node.nodeId(), node.name(), "blocking", "pending", task.createdBy(), null,
                    now, expires, null, null, null));
        }
    }

    private void dispatchAgent(TaskRepository.NodeRow node, TaskGraph.GraphNode wf,
                               String parentRunId) {
        List<io.github.hopewang123456.mailbus.identity.Employee> candidates =
                staff.pickCandidates(wf, "agent");
        if (candidates.isEmpty()) {
            return;
        }
        Instant now = Instant.now();
        int fanout = fanout(wf);
        boolean shortFanout = fanout > 1 && candidates.size() < fanout;
        int attempt = repo.maxAttempt(task.taskId(), node.nodeId()) + 1;
        String group = fanout > 1 ? task.taskId() + ":" + node.nodeId() + ":" + attempt : null;
        List<io.github.hopewang123456.mailbus.identity.Employee> workers =
                candidates.subList(0, Math.min(fanout, candidates.size()));
        TaskRepository.RunRow latest = null;
        for (int index = 0; index < workers.size(); index++) {
            int slot = fanout > 1 ? index + 1 : 0;
            latest = new TaskRepository.RunRow(ids.next("run"), task.taskId(), node.nodeId(),
                    attempt, slot, workers.get(index).employeeId(), null, "dispatched", group,
                    shortFanout, null, parentRunId, now, null, null,
                    now.plusSeconds(timeout(wf)), null);
            repo.addRun(latest);
        }
        saveNode(node.withState("running", latest == null ? null : latest.runId(), now));
        markRunning();
    }

    // ---- 结果与失败 ----

    public void complete(TaskRepository.RunRow run, String result) {
        Instant now = Instant.now();
        repo.saveRun(run.withSubmission(run.assignedEmployeeId(), "done", run.startedAt(),
                now, result));
        TaskRepository.NodeRow node = nodes.get(run.nodeId());
        if (fanout(run.nodeId()) > 1) {
            if (slotsSettled(run.nodeId())) {
                saveNode(node.withState(fanoutState(run.nodeId()), node.currentRunId(), now));
                advance(run.nodeId());
            } else {
                saveNode(node.withState("running", node.currentRunId(), now));
            }
            settle();
            return;
        }
        repo.deleteArtifactsForNodeExcept(task.taskId(), run.nodeId(), run.runId());
        saveNode(node.withState("done", run.runId(), now));
        advance(run.nodeId());
        settle();
    }

    public void fail(TaskRepository.RunRow run, String result) {
        Instant now = Instant.now();
        repo.saveRun(run.withSubmission(run.assignedEmployeeId(), "failed", run.startedAt(),
                now, result));
        TaskGraph.GraphNode wf = wf(run.nodeId());
        int attempts = 0;
        for (TaskRepository.RunRow item : repo.runsByNode(task.taskId(), run.nodeId())) {
            if (item.fanoutSlot() == run.fanoutSlot()) {
                attempts++;
            }
        }
        if (wf != null && attempts <= wf.maxRetries()) {
            if (fanout(run.nodeId()) > 1) {
                retrySlot(run, wf);
            } else {
                saveNode(nodes.get(run.nodeId()).withState("pending", null, now));
                dispatch(run.nodeId(), 0, null);
            }
            return;
        }
        escalate("run_failed", run.nodeId(), run.runId(), null, 1);
        if (fanout(run.nodeId()) > 1) {
            saveNode(nodes.get(run.nodeId()).withState("failed", null, now));
            settle();
            return;
        }
        blockWithHuman(run.nodeId(), wf);
    }

    private void retrySlot(TaskRepository.RunRow run, TaskGraph.GraphNode wf) {
        Instant now = Instant.now();
        int attempt = repo.maxAttempt(task.taskId(), run.nodeId()) + 1;
        TaskRepository.RunRow fresh = run.retry(ids.next("run"), attempt, now,
                now.plusSeconds(timeout(wf)));
        repo.addRun(fresh);
        saveNode(nodes.get(run.nodeId()).withState("running", fresh.runId(), now));
    }

    // ---- 汇聚与收尾 ----

    public void settle() {
        if (Set.of("done", "cancelled", "failed").contains(task.state())) {
            return;
        }
        if (blocked) {
            return;
        }
        List<TaskRepository.RunRow> runs = repo.runsByTask(task.taskId());
        if (runs.stream().anyMatch(item -> OPEN_RUN_STATES.contains(item.state()))) {
            markRunning();
            return;
        }
        if (nodes.values().stream().allMatch(node -> TERMINAL_NODE_STATES.contains(node.state()))) {
            saveTask(task.withState("done", Instant.now()));
        } else {
            markRunning();
        }
    }

    public void advance(String nodeId) {
        if (graph == null) {
            return;
        }
        List<TaskGraph.Edge> edges = graph.forwardEdges(nodeId);
        if (edges.isEmpty()) {
            return;
        }
        List<String> targets = select(edges, nodeId);
        if (targets == null) {
            terminate("no_matching_branch");
            return;
        }
        for (String target : targets) {
            dispatch(target, 0, null);
        }
    }

    private List<String> select(List<TaskGraph.Edge> edges, String nodeId) {
        if (edges.size() == 1) {
            TaskGraph.Edge edge = edges.get(0);
            if (edge.condition() == null || edge.condition().isBlank()) {
                return List.of(edge.toNodeId());
            }
            return conditions.evaluate(edge.condition(), context(nodeId))
                    ? List.of(edge.toNodeId()) : null;
        }
        List<TaskGraph.Edge> conditioned = edges.stream()
                .filter(edge -> edge.condition() != null && !edge.condition().isBlank()).toList();
        if (conditioned.isEmpty()) {
            return edges.stream().map(TaskGraph.Edge::toNodeId).toList();
        }
        Map<String, Object> context = context(nodeId);
        for (TaskGraph.Edge edge : conditioned) {
            if (conditions.evaluate(edge.condition(), context)) {
                return List.of(edge.toNodeId());
            }
        }
        return null;
    }

    public void terminate(String reason) {
        Instant now = Instant.now();
        for (TaskRepository.RunRow run : repo.runsByTask(task.taskId())) {
            if (OPEN_RUN_STATES.contains(run.state())) {
                repo.saveRun(run.withState("skipped", now));
            }
        }
        for (TaskRepository.NodeRow node : List.copyOf(nodes.values())) {
            if (!TERMINAL_NODE_STATES.contains(node.state())) {
                saveNode(node.withState("skipped", null, now));
            }
        }
        withdrawApprovals();
        saveTask(task.withTermination(reason, now).withState("cancelled", now));
    }

    // ---- 升级与阻塞 ----

    public void escalate(String reason, String nodeId, String runId, String approvalId,
                         int level) {
        if (repo.hasOpenEscalation(task.taskId(), reason)) {
            return;
        }
        String target = "super_admin";
        if (task.ownerId() != null) {
            String leader = repo.teamLeaderOfEmployee(task.ownerId());
            if (leader != null) {
                target = leader;
            }
        }
        repo.addEscalation(ids.next("esc"), task.taskId(), reason, target, Instant.now(),
                runId, approvalId, level);
    }

    private void blockWithHuman(String nodeId, TaskGraph.GraphNode wf) {
        TaskRepository.NodeRow node = nodes.get(nodeId);
        Instant now = Instant.now();
        TaskRepository.RunRow run = new TaskRepository.RunRow(ids.next("run"), task.taskId(),
                nodeId, repo.maxAttempt(task.taskId(), nodeId) + 1, 0, null, null,
                "waiting_human", null, false, "{\"escalated\":true}", null, now, null, null,
                now.plusSeconds(wf == null ? 0 : timeout(wf)), null);
        repo.addRun(run);
        saveNode(node.withState("blocked", run.runId(), now));
        blocked = true;
        saveTask(task.withState("blocked", now));
    }

    private boolean forced(String nodeId) {
        List<TaskRepository.RunRow> runs = repo.runsByNode(task.taskId(), nodeId);
        int latest = runs.stream().mapToInt(TaskRepository.RunRow::attemptNo).max().orElse(0);
        for (TaskRepository.RunRow run : runs) {
            if (run.attemptNo() != latest || run.result() == null) {
                continue;
            }
            Object payload = conditions.parseResult(run.result());
            if (payload instanceof Map<?, ?> map && Boolean.TRUE.equals(map.get("forced"))) {
                return true;
            }
        }
        return false;
    }

    private boolean enterLoop(TaskRepository.NodeRow node, TaskGraph.GraphNode wf) {
        Map<String, Integer> counters = new LinkedHashMap<>(task.loopCounters());
        int count = counters.getOrDefault(node.nodeId(), 0) + 1;
        counters.put(node.nodeId(), count);
        saveTask(task.withLoopCounters(counters, Instant.now()));
        if (count <= wf.maxLoops()) {
            saveNode(node.withState("pending", null, Instant.now()));
            return false;
        }
        escalate("loop_exceeded", node.nodeId(), null, null, 1);
        blockWithHuman(node.nodeId(), wf);
        return true;
    }

    public void reject(String nodeId) {
        List<TaskGraph.Edge> edges = graph == null ? List.of() : graph.backEdges(nodeId);
        if (edges.isEmpty()) {
            terminate("approval_rejected");
            return;
        }
        saveNode(nodes.get(nodeId).withState("pending", null, Instant.now()));
        dispatch(edges.get(0).fromNodeId(), 0, null);
        settle();
    }

    public void approve(String nodeId) {
        saveNode(nodes.get(nodeId).withState("done", nodes.get(nodeId).currentRunId(),
                Instant.now()));
        advance(nodeId);
        settle();
    }

    // ---- 汇聚 ----

    public record JoinState(boolean ready, List<String> missing) {
    }

    public JoinState joinState(String nodeId) {
        List<TaskRepository.RunRow> runs = repo.runsByTask(task.taskId());
        List<String> missing = new ArrayList<>();
        boolean ready = true;
        for (String pred : graph == null ? List.<String>of() : graph.predecessors(nodeId)) {
            List<TaskRepository.RunRow> predRuns = runs.stream()
                    .filter(item -> item.nodeId().equals(pred)).toList();
            if (predRuns.isEmpty()) {
                missing.add(pred + ":none");
                ready = false;
                continue;
            }
            List<TaskRepository.RunRow> latest = latestBySlot(predRuns);
            int fanout = fanout(pred);
            boolean shortFanout = latest.stream().anyMatch(TaskRepository.RunRow::shortFanout);
            if (fanout > 1 && latest.size() < fanout && !shortFanout) {
                missing.add(pred + ":short");
                ready = false;
            }
            for (TaskRepository.RunRow item : latest) {
                if (!TERMINAL_RUN_STATES.contains(item.state())) {
                    ready = false;
                }
                if ("failed".equals(item.state()) || "skipped".equals(item.state())) {
                    String slot = fanout > 1 ? ":slot" + item.fanoutSlot() : "";
                    missing.add(pred + slot + ":" + item.state());
                    ready = false;
                }
            }
        }
        return new JoinState(ready, missing);
    }

    private void join(String nodeId) {
        TaskRepository.NodeRow node = nodes.get(nodeId);
        JoinState state = joinState(nodeId);
        if (!state.ready()) {
            saveNode(node.withState("pending", null, Instant.now()));
            return;
        }
        Instant now = Instant.now();
        int attempt = repo.maxAttempt(task.taskId(), nodeId) + 1;
        TaskRepository.RunRow run = new TaskRepository.RunRow(ids.next("run"), task.taskId(),
                nodeId, attempt, 0, null, null, "done", null, false,
                json(Map.of("missing", state.missing(), "forced", false)), null,
                now, now, now, null, null);
        repo.addRun(run);
        saveNode(node.withState("done", run.runId(), now));
        advance(nodeId);
        settle();
    }

    public List<String> forceJoin(String nodeId, String group, String scope) {
        JoinState state = joinState(nodeId);
        Instant now = Instant.now();
        int attempt = repo.maxAttempt(task.taskId(), nodeId) + 1;
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("missing", state.missing());
        payload.put("forced", true);
        payload.put("fanout_group", group);
        payload.put("scope", scope);
        TaskRepository.RunRow run = new TaskRepository.RunRow(ids.next("run"), task.taskId(),
                nodeId, attempt, 0, null, null, "done", null, false, json(payload), null,
                now, now, now, null, null);
        repo.addRun(run);
        lastAttempt = attempt;
        saveNode(nodes.get(nodeId).withState("done", run.runId(), now));
        if ("downstream".equals(scope)) {
            advance(nodeId);
        }
        settle();
        return state.missing();
    }

    private boolean slotsSettled(String nodeId) {
        List<TaskRepository.RunRow> latest = latestBySlot(
                repo.runsByNode(task.taskId(), nodeId));
        return !latest.isEmpty()
                && latest.stream().allMatch(item -> TERMINAL_RUN_STATES.contains(item.state()));
    }

    private String fanoutState(String nodeId) {
        List<TaskRepository.RunRow> latest = latestBySlot(
                repo.runsByNode(task.taskId(), nodeId));
        if (!latest.isEmpty() && latest.stream().allMatch(item -> "done".equals(item.state()))) {
            return "done";
        }
        return "failed";
    }

    private List<TaskRepository.RunRow> latestBySlot(List<TaskRepository.RunRow> runs) {
        Map<Integer, TaskRepository.RunRow> latest = new LinkedHashMap<>();
        for (TaskRepository.RunRow run : runs) {
            TaskRepository.RunRow current = latest.get(run.fanoutSlot());
            if (current == null || run.attemptNo() > current.attemptNo()) {
                latest.put(run.fanoutSlot(), run);
            }
        }
        return new ArrayList<>(latest.values());
    }

    // ---- 小工具 ----

    private TaskGraph.GraphNode wf(String nodeId) {
        return graph == null ? null : graph.node(nodeId);
    }

    private int fanout(String nodeId) {
        TaskGraph.GraphNode wf = wf(nodeId);
        return wf == null ? 1 : fanout(wf);
    }

    private int fanout(TaskGraph.GraphNode wf) {
        Object value = wf.config().get("fanout");
        if (value == null) {
            return 1;
        }
        try {
            return Math.max(1, Integer.parseInt(value.toString().split("\\.")[0]));
        } catch (NumberFormatException exception) {
            return 1;
        }
    }

    private long timeout(TaskGraph.GraphNode wf) {
        if (wf == null || wf.timeoutSeconds() == null || wf.timeoutSeconds() <= 0) {
            return DEFAULT_WORK_TIMEOUT_SECONDS;
        }
        return wf.timeoutSeconds();
    }

    private Map<String, Object> context(String nodeId) {
        List<TaskRepository.RunRow> runs = repo.runsByNode(task.taskId(), nodeId);
        TaskRepository.RunRow latest = runs.stream()
                .max((left, right) -> Integer.compare(left.attemptNo(), right.attemptNo()))
                .orElse(null);
        Map<String, Object> taskContext = new HashMap<>();
        taskContext.put("title", task.title());
        taskContext.put("state", task.state());
        taskContext.put("workflow_id", task.workflowId());
        Map<String, Object> nodeContext = new HashMap<>();
        nodeContext.put("node_id", nodeId);
        nodeContext.put("name", nodes.containsKey(nodeId) ? nodes.get(nodeId).name() : nodeId);
        Map<String, Object> context = new HashMap<>();
        context.put("result", latest == null ? null : conditions.parseResult(latest.result()));
        context.put("task", taskContext);
        context.put("node", nodeContext);
        context.put("context", Map.of());
        context.put("artifacts", repo.artifactCount(task.taskId()));
        return context;
    }

    private void markRunning() {
        if (!Set.of("running", "done", "cancelled").contains(task.state())) {
            saveTask(task.withState("running", Instant.now()));
        }
    }

    private void saveTask(TaskRepository.TaskRow next) {
        task = next;
        repo.saveTask(task);
    }

    private void saveNode(TaskRepository.NodeRow node) {
        TaskRepository.NodeRow saved = new TaskRepository.NodeRow(node.taskId(), node.nodeId(),
                node.name(), node.seq(), node.state(), node.currentRunId(), Instant.now());
        nodes.put(saved.nodeId(), saved);
        repo.saveNode(saved);
    }

    private void withdrawApprovals() {
        for (TaskRepository.ApprovalRow item : repo.pendingApprovals(task.taskId())) {
            repo.saveApproval(item.resolved("withdrawn", task.createdBy(), null, Instant.now()));
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            return "{}";
        }
    }
}
