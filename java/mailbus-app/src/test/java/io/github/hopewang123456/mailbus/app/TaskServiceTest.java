package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2a 任务引擎 — POST /api/tasks/create 全路径 + FSM 动作集
 * （python create_task_from_envelope / task_fsm 对等；任务文件双栈共享）。
 */
class TaskServiceTest {

    @TempDir
    Path dataDir;

    private TaskService svc;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {"1": {"key": "designer", "display": {"zh": "方案设计师"},
                                  "candidates": ["agentA", "agentB"]},
                           "8": {"key": "developer", "display": {"zh": "开发工程师"},
                                  "candidates": ["agentB"]}}}
                """);
        Files.writeString(dataDir.resolve("config.json"), """
                {"agents": {"agentA": {"concurrency": 1}, "agentB": {"concurrency": 1}}}
                """);
        Files.createDirectories(dataDir.resolve("inbox/agentA"));
        Files.createDirectories(dataDir.resolve("inbox/agentB"));
        repo = new FileTaskRepository(dataDir);
        Clock clock = Clock.systemUTC();
        svc = new TaskService(dataDir, clock, repo,
                new RoleResolverService(dataDir, repo),
                new HumanQueueService(dataDir, clock));
    }

    private Map<String, Object> envelope(String taskId, String tier) {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("task_id", taskId);
        env.put("intent", "设计一个数据面板");
        env.put("initiator", "ziyan");
        env.put("mode", "explicit");
        env.put("tier", tier);
        env.put("planned_chain", List.of(
                Map.of("role_type", 1),
                Map.of("role_type", 8)));
        return env;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> taskFile(String taskId) {
        return repo.find(taskId).orElseThrow();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> inboxMessages(String agent) {
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("inbox/" + agent + "/inbox.json"));
        return doc == null ? List.of() : (List<Map<String, Object>>) (List<?>) doc.getOrDefault("messages", List.of());
    }

    // ── create 路径 ─────────────────────────────────────────────────────────

    @Test
    void legacyBodyRejected410() {
        TaskService.Result r = svc.createFromEnvelope(Map.of("title", "x", "assignee", "agentA"));
        assertEquals(410, r.status());
        assertEquals("legacy_deprecated", r.body().get("error"));
    }

    @Test
    void schemaInvalid400() {
        Map<String, Object> bad = new LinkedHashMap<>();
        bad.put("task_id", "t-1"); // 缺 intent/initiator/mode/tier
        TaskService.Result r = svc.createFromEnvelope(bad);
        assertEquals(400, r.status());
        assertEquals("schema_invalid", r.body().get("error"));
        assertTrue(((List<?>) r.body().get("details")).size() >= 3);
    }

    @Test
    void autoModeUnsupported400() {
        Map<String, Object> env = envelope("t-auto", "S");
        env.put("mode", "auto");
        env.remove("planned_chain");
        TaskService.Result r = svc.createFromEnvelope(env);
        assertEquals(400, r.status());
        assertEquals("auto_plan_unsupported", r.body().get("error"));
    }

    @Test
    void duplicateTaskId409() {
        assertEquals(201, svc.createFromEnvelope(envelope("t-dup", "S")).status());
        TaskService.Result r = svc.createFromEnvelope(envelope("t-dup", "S"));
        assertEquals(409, r.status());
        assertEquals("task_exists", r.body().get("error"));
    }

    @Test
    void tierSCreatesAndDispatchesFirstStep() {
        TaskService.Result r = svc.createFromEnvelope(envelope("t-s1", "S"));
        assertEquals(201, r.status());
        assertEquals("ok", r.body().get("status"));

        Map<String, Object> task = taskFile("t-s1");
        assertEquals("running", task.get("status"));
        Map<String, Object> fsm = (Map<String, Object>) task.get("fsm");
        assertEquals("executing", fsm.get("state"));

        List<Map<String, Object>> chain = (List<Map<String, Object>>) (List<?>) task.get("chain");
        assertEquals(1, chain.size());
        Map<String, Object> step = chain.get(0);
        assertEquals("s1", step.get("step_id"));
        assertEquals("dispatched", step.get("fsm_state")); // 派发成功后标记
        assertEquals(List.of(8), step.get("planned_role_types")); // 其余职位进 head
        Map<String, Object> meta = (Map<String, Object>) step.get("dispatch_meta");
        assertEquals("idle_first", meta.get("source"));
        assertEquals("agentA", step.get("to_agent"));
        assertEquals("agentA", task.get("assignee"));

        // inbox 真收到 + work-order 落盘
        List<Map<String, Object>> msgs = inboxMessages("agentA");
        assertEquals(1, msgs.size());
        assertEquals("task", msgs.get(0).get("type"));
        assertEquals("t-s1", msgs.get(0).get("task_id"));
        assertTrue(Files.isRegularFile(dataDir.resolve("work-orders/t-s1/step-s1.md")));
    }

    @Test
    void tierMWaitsPlanApprovalWithHumanQueue() {
        TaskService.Result r = svc.createFromEnvelope(envelope("t-plan", "M"));
        assertEquals(201, r.status());
        String hid = (String) r.body().get("human_queue_id");
        assertTrue(hid.startsWith("hq-"));

        Map<String, Object> task = taskFile("t-plan");
        assertEquals("pending", task.get("status"));
        Map<String, Object> fsm = (Map<String, Object>) task.get("fsm");
        assertEquals("created", fsm.get("state"));
        assertEquals("await_plan_approval", fsm.get("substate"));
        assertEquals(hid, fsm.get("human_queue_id"));

        Map<String, Object> queue = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        List<Map<String, Object>> items = (List<Map<String, Object>>) (List<?>) queue.get("items");
        assertEquals(1, items.size());
        assertEquals("plan_approval", items.get(0).get("type"));
        // 待批阶段不派发
        assertTrue(inboxMessages("agentA").isEmpty());
    }

    @Test
    void awaitPlanApprovalOverrideForcesGate() {
        Map<String, Object> env = envelope("t-force", "S");
        env.put("await_plan_approval", true);
        TaskService.Result r = svc.createFromEnvelope(env);
        assertEquals(201, r.status());
        assertNotNull(r.body().get("human_queue_id"));
        assertEquals("created",
                ((Map<?, ?>) taskFile("t-force").get("fsm")).get("state"));
    }

    // ── fsm 动作 ────────────────────────────────────────────────────────────

    @Test
    void approvePlanDispatchesAndClosesQueue() {
        svc.createFromEnvelope(envelope("t-ap", "M"));
        TaskService.Result r = svc.fsmAction("t-ap", "approve-plan",
                Map.of("decision", "approved", "reviewer", "ziyan"));
        assertEquals(200, r.status());
        assertEquals(Boolean.TRUE, r.body().get("dispatch_ok"));
        assertEquals("executing",
                ((Map<?, ?>) r.body().get("fsm")).get("fsm_state"));
        assertEquals(1, inboxMessages("agentA").size());

        Map<String, Object> queue = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        List<Map<String, Object>> items = (List<Map<String, Object>>) (List<?>) queue.get("items");
        assertEquals("resolved", items.get(0).get("status"));
        Map<String, Object> task = taskFile("t-ap");
        assertNull(((Map<?, ?>) task.get("fsm")).get("human_queue_id"));
    }

    @Test
    void approvePlanDeniedNeedsReasonThenCancels() {
        svc.createFromEnvelope(envelope("t-deny", "M"));
        TaskService.Result noReason = svc.fsmAction("t-deny", "approve-plan",
                Map.of("decision", "denied"));
        assertEquals(400, noReason.status());
        assertEquals("missing_reason", noReason.body().get("error"));

        TaskService.Result r = svc.fsmAction("t-deny", "approve-plan",
                Map.of("decision", "denied", "reason", "方案太粗"));
        assertEquals(200, r.status());
        assertEquals("cancelled", taskFile("t-deny").get("status"));
    }

    @Test
    void rollbackCreatesAttemptTwoAndRedispatches() {
        svc.createFromEnvelope(envelope("t-rb", "S"));
        TaskService.Result r = svc.fsmAction("t-rb", "rollback",
                Map.of("to_step", 1, "reason", "结果不合格"));
        assertEquals(200, r.status());
        assertEquals(Boolean.TRUE, r.body().get("dispatch_ok"));

        List<Map<String, Object>> chain =
                (List<Map<String, Object>>) (List<?>) taskFile("t-rb").get("chain");
        assertEquals(2, chain.size());
        Map<String, Object> redo = chain.get(1);
        assertEquals("s1a2", redo.get("step_id"));
        assertEquals(2, ((Number) redo.get("attempt")).intValue());
        assertEquals("s1", redo.get("rollback_from"));
        assertEquals("queued".equals(redo.get("fsm_state")) ? "queued" : "dispatched",
                redo.get("fsm_state")); // 派发成功后 dispatched
        assertEquals(2, inboxMessages("agentA").size());
    }

    @Test
    void rollbackWithoutTargetFails400() {
        svc.createFromEnvelope(envelope("t-rb404", "S"));
        TaskService.Result r = svc.fsmAction("t-rb404", "rollback", Map.of("to_step", 9));
        assertEquals(400, r.status());
        assertEquals("rollback_target_not_found", r.body().get("error"));
    }

    @Test
    void pauseResumeCancelPriorityLifecycle() {
        svc.createFromEnvelope(envelope("t-lc", "S"));
        assertEquals(200, svc.fsmAction("t-lc", "pause", Map.of("reason", "等等")).status());
        assertEquals("paused", taskFile("t-lc").get("status"));

        assertEquals(200, svc.fsmAction("t-lc", "resume", Map.of()).status());
        assertEquals("running", taskFile("t-lc").get("status"));

        TaskService.Result p = svc.fsmAction("t-lc", "priority", Map.of("priority", 10));
        assertEquals(200, p.status());
        assertEquals(10, ((Number) ((Map<?, ?>) p.body().get("fsm")).get("priority")).intValue());

        assertEquals(200, svc.fsmAction("t-lc", "cancel", Map.of("reason", "不要了")).status());
        assertEquals("cancelled", taskFile("t-lc").get("status"));
        assertEquals("cancelled",
                ((Map<?, ?>) taskFile("t-lc").get("fsm")).get("state"));
    }

    @Test
    void skipMarksActiveStepSkipped() {
        svc.createFromEnvelope(envelope("t-skip", "S"));
        TaskService.Result r = svc.fsmAction("t-skip", "skip", Map.of("reason", "跳过"));
        assertEquals(200, r.status());
        assertEquals(Boolean.TRUE, r.body().get("needs_manual_advance"));
        List<Map<String, Object>> chain =
                (List<Map<String, Object>>) (List<?>) taskFile("t-skip").get("chain");
        assertEquals("skipped", chain.get(0).get("fsm_state"));
    }

    @Test
    void unknownTask404AndFutureActions501() {
        assertEquals(404, svc.fsmAction("nope", "cancel", Map.of()).status());

        svc.createFromEnvelope(envelope("t-501", "S"));
        assertEquals(501, svc.fsmAction("t-501", "approve-join", Map.of()).status());
        assertEquals(501, svc.fsmAction("t-501", "continue", Map.of()).status());
    }

    @Test
    void listTasksFiltersAndPaginates() {
        svc.createFromEnvelope(envelope("t-list-1", "S"));
        svc.createFromEnvelope(envelope("t-list-2", "S"));
        svc.fsmAction("t-list-2", "cancel", Map.of("reason", "x"));

        Map<String, Object> all = svc.listTasks(null, null, 120, 0);
        assertEquals(2, ((Number) all.get("total")).intValue());

        Map<String, Object> running = svc.listTasks("running", null, 120, 0);
        assertEquals(1, ((Number) running.get("total")).intValue());
        assertEquals("t-list-1",
                ((List<Map<String, Object>>) running.get("tasks")).get(0).get("task_id"));

        Map<String, Object> page = svc.listTasks(null, null, 1, 1);
        assertEquals(1, ((Number) page.get("count")).intValue());
        assertEquals(2, ((Number) page.get("total")).intValue());
    }

    @Test
    void autoModePlansViaTier0Rules() {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("task_id", "t-auto1");
        env.put("intent", "做一个数据面板");
        env.put("initiator", "ziyan");
        env.put("mode", "auto");
        env.put("tier", "S");
        env.put("task_type", "feature");
        // 未注入 planner（单测上下文）→ 400
        assertEquals(400, svc.createFromEnvelope(env).status());

        svc.setPlanner(new TaskPlannerService(dataDir, null));
        TaskService.Result r = svc.createFromEnvelope(env);
        assertEquals(201, r.status());
        Map<String, Object> task = taskFile("t-auto1");
        List<Map<String, Object>> chain = (List<Map<String, Object>>) (List<?>) task.get("chain");
        assertEquals(1, ((Number) chain.get(0).get("role_type")).intValue()); // feature → [1]
        assertEquals("rules", ((Map<?, ?>) task.get("plan_meta")).get("method"));
        assertEquals("agentA", task.get("assignee")); // 职位 1 候选池派发
    }

    @Test
    void fsmSummaryShapeMatchesPythonContract() {
        svc.createFromEnvelope(envelope("t-sum", "S"));
        Map<String, Object> summary = svc.fsmSummary("t-sum").orElseThrow();
        assertEquals("t-sum", summary.get("task_id"));
        assertEquals("executing", summary.get("fsm_state"));
        assertEquals("s1", summary.get("active_step_id"));
        Map<String, Object> active = (Map<String, Object>) summary.get("active_step");
        assertEquals("agentA", active.get("to_person"));
        List<Map<String, Object>> steps = (List<Map<String, Object>>) summary.get("steps");
        assertEquals(1, steps.size());
        assertEquals("msg-results/t-sum/step-s1.json", steps.get(0).get("result_ref"));
    }
}
