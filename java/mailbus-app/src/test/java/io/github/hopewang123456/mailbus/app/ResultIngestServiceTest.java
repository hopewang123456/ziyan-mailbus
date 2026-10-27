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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2b 结果消化 — apply_submit/trigger/accept 对等
 * （advance / planned 消费 / role-flow SoT / 终态 auto-accept / verify 阻塞）。
 */
class ResultIngestServiceTest {

    @TempDir
    Path dataDir;

    private TaskService svc;
    private ResultIngestService ingest;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {
                  "1": {"key": "designer", "display": {"zh": "方案设计师"}, "candidates": ["agentA", "agentB"]},
                  "8": {"key": "developer", "display": {"zh": "开发工程师"}, "candidates": ["agentB"]},
                  "12": {"key": "acceptor", "display": {"zh": "验收员"}, "candidates": ["agentC"]}}}
                """);
        Files.writeString(dataDir.resolve("roles/json/role-flow.json"), """
                {"transitions": [{"from_role_type": 1, "conclusion": "done", "to_role_type": 8}],
                 "terminal": [{"role_type": 12, "conclusion": "approved"},
                              {"role_type": 8, "conclusion": "done"}],
                 "blocked_fallback_role_type": 1}
                """);
        Files.writeString(dataDir.resolve("config.json"), """
                {"agents": {"agentA": {"concurrency": 1}, "agentB": {"concurrency": 1}, "agentC": {}}}
                """);
        for (String a : List.of("agentA", "agentB", "agentC")) {
            Files.createDirectories(dataDir.resolve("inbox/" + a));
        }
        repo = new FileTaskRepository(dataDir);
        Clock clock = Clock.systemUTC();
        var resolver = new RoleResolverService(dataDir, repo);
        var humanQueue = new HumanQueueService(dataDir, clock);
        svc = new TaskService(dataDir, clock, repo, resolver, humanQueue);
        ingest = new ResultIngestService(dataDir, clock, repo, resolver, humanQueue);
    }

    private void createTask(String id, String tier, List<Map<String, Object>> planned) {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("task_id", id);
        env.put("intent", "冒烟链路");
        env.put("initiator", "ziyan");
        env.put("mode", "explicit");
        env.put("tier", tier);
        env.put("planned_chain", planned);
        assertEquals(201, svc.createFromEnvelope(env).status());
    }

    private Map<String, Object> stepResult(String conclusion, String agent, Map<String, Object> extra) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("conclusion", conclusion);
        r.put("summary", "本步完成");
        r.put("agent", agent);
        if (extra != null) {
            r.putAll(extra);
        }
        return r;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> chain(String taskId) {
        return (List<Map<String, Object>>) (List<?>) repo.find(taskId).orElseThrow().get("chain");
    }

    @Test
    void submitAdvancesToNextPlannedRoleAndDispatches() {
        createTask("t-adv", "S", List.of(Map.of("role_type", 1), Map.of("role_type", 8)));

        Map<String, Object> out = ingest.submitStepResult("agentA",
                Map.of("task_id", "t-adv", "step_id", "s1", "conclusion", "done", "summary", "方案好了"));
        assertEquals(200, ((Number) out.get("status")).intValue());

        List<Map<String, Object>> chain = chain("t-adv");
        assertEquals(2, chain.size());
        assertEquals("completed", chain.get(0).get("fsm_state"));
        assertEquals(Boolean.TRUE, chain.get(0).get("result_consumed"));
        // planned 消费：head.planned_role_types 弹出 8
        assertEquals(List.of(), chain.get(0).get("planned_role_types"));
        Map<String, Object> s2 = chain.get(1);
        assertEquals("s2", s2.get("step_id"));
        assertEquals(8, ((Number) s2.get("role_type")).intValue());
        assertEquals("agentB", s2.get("to_agent"));
        assertEquals("dispatched", s2.get("fsm_state"));
        // agentB inbox 收到第二步消息（G-02 立即推进）
        Map<String, Object> inboxB = JsonFiles.readMap(dataDir.resolve("inbox/agentB/inbox.json"));
        assertEquals(1, ((List<?>) inboxB.get("messages")).size());
    }

    @Test
    void plannedEmptyThenTerminalEntersAcceptingAndAcceptSucceeds() {
        // tier=S 单步 rt8：建单即派发（无 plan_approval 闸）；terminal (8, done) 命中
        // 后 S 级不走 auto-accept（仅 rt12）→ accepting + final_acceptance
        createTask("t-term", "S", List.of(Map.of("role_type", 8)));
        ingest.submitStepResult("agentB",
                Map.of("task_id", "t-term", "step_id", "s1", "conclusion", "done"));

        Map<String, Object> task = repo.find("t-term").orElseThrow();
        // terminal (8, done) 命中 + tier=M → accepting + final_acceptance 待办
        assertEquals("accepting", ((Map<?, ?>) task.get("fsm")).get("state"));
        assertEquals("pending", task.get("status"));
        Map<String, Object> queue = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        assertEquals("final_acceptance",
                ((List<Map<String, Object>>) (List<?>) queue.get("items")).get(0).get("type"));

        TaskService.Result r = svc.fsmAction("t-term", "accept",
                Map.of("decision", "approved", "reviewer", "ziyan"));
        assertEquals(200, r.status());
        assertEquals("success", repo.find("t-term").orElseThrow().get("status"));
        assertTrue(Files.isRegularFile(dataDir.resolve("msg-results/t-term/acceptance.json")));
        Map<String, Object> queueAfter = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        assertEquals("resolved",
                ((List<Map<String, Object>>) (List<?>) queueAfter.get("items")).get(0).get("status"));
    }

    @Test
    void sTierRoleTwelveApprovedAutoAccepts() {
        createTask("t-auto", "S", List.of(Map.of("role_type", 12)));
        ingest.submitStepResult("agentC",
                Map.of("task_id", "t-auto", "step_id", "s1", "conclusion", "approved"));

        Map<String, Object> task = repo.find("t-auto").orElseThrow();
        assertEquals("success", task.get("status"));
        assertEquals("succeeded", ((Map<?, ?>) task.get("fsm")).get("state"));
        Map<String, Object> acc = JsonFiles.readMap(dataDir.resolve("msg-results/t-auto/acceptance.json"));
        assertEquals("auto", acc.get("method"));
    }

    @Test
    void roleFlowTransitionAdvancesWhenNoPlanned() {
        createTask("t-flow", "M", List.of(Map.of("role_type", 1)));
        ingest.submitStepResult("agentA",
                Map.of("task_id", "t-flow", "step_id", "s1", "conclusion", "done"));

        // planned 空 → role-flow transition (1, done → 8) → advance
        List<Map<String, Object>> chain = chain("t-flow");
        assertEquals(2, chain.size());
        assertEquals(8, ((Number) chain.get(1).get("role_type")).intValue());
        assertEquals("executing", ((Map<?, ?>) repo.find("t-flow").orElseThrow().get("fsm")).get("state"));
    }

    @Test
    void wrongAgentResultIsRejectedByIngest() {
        createTask("t-wa", "S", List.of(Map.of("role_type", 1)));
        Map<String, Object> out = ingest.submitStepResult("agentB",
                Map.of("task_id", "t-wa", "step_id", "s1", "conclusion", "done"));
        assertEquals(200, ((Number) out.get("status")).intValue());
        // wrong_agent → 不推进：单步链、step 未完成
        Map<String, Object> out2 = (Map<String, Object>) ((Map<String, Object>) out.get("body")).get("ingest");
        assertEquals("wrong_agent", out2.get("skipped"));
        assertEquals(1, chain("t-wa").size());
        assertEquals("dispatched", chain("t-wa").get(0).get("fsm_state"));
    }

    @Test
    void invalidConclusionRejected400() {
        Map<String, Object> out = ingest.submitStepResult("agentA",
                Map.of("task_id", "x", "step_id", "s1", "conclusion", "maybe"));
        assertEquals(400, ((Number) out.get("status")).intValue());
        assertEquals("invalid_conclusion", ((Map<?, ?>) out.get("body")).get("error"));
    }

    @Test
    void verifyFailureBlocksTask() throws IOException {
        createTask("t-ver", "M", List.of(Map.of("role_type", 8)));
        // 直接落结果文件（agent 自写路径）再 ingest —— dev done + self_test=fail
        new StepResultIo(dataDir).writeStepResult("t-ver", "s1",
                stepResult("done", "agentB", Map.of("details", Map.of("self_test", "fail"))),
                "agentB", 8, Clock.systemUTC().instant().toString());

        Map<String, Object> out = ingest.ingestTask("t-ver");
        assertEquals("blocked", out.get("action"));
        assertEquals("self_test failed", out.get("reason"));
        Map<String, Object> task = repo.find("t-ver").orElseThrow();
        assertEquals("blocked", ((Map<?, ?>) task.get("fsm")).get("state"));
    }

    @Test
    void scanAllAdvancesExecutingTasks() {
        createTask("t-scan", "S", List.of(Map.of("role_type", 1), Map.of("role_type", 8)));
        ingest.submitStepResult("agentA",
                Map.of("task_id", "t-scan", "step_id", "s1", "conclusion", "done"));

        Map<String, Object> out = ingest.scanAll();
        assertEquals(0, ((Number) out.get("advanced")).intValue()); // 已消化，scan 空转
        assertEquals("executing", ((Map<?, ?>) repo.find("t-scan").orElseThrow().get("fsm")).get("state"));
    }
}
