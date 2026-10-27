package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * M2c 发令窗口聚合 — draft 预演（422/503/200）+ command/inbox 四路
 * （manager-pending 三桶 / human-queue 去重 / alerts / 子言未读）。
 */
class CommandEndpointsTest {

    @TempDir
    Path dataDir;

    private CommandDraftService draft;
    private CommandInboxService inbox;
    private io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository repo;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {"1": {"display": {"zh": "方案设计师"}}, "8": {}}}
                """);
        Files.writeString(dataDir.resolve("config.json"), "{\"agents\": {\"agentA\": {}}}");
        Files.createDirectories(dataDir.resolve("inbox/agentA"));
        Files.createDirectories(dataDir.resolve("inbox/ziyan"));
        repo = new io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository(dataDir);
        Clock clock = Clock.systemUTC();
        var humanQueue = new HumanQueueService(dataDir, clock);
        draft = new CommandDraftService(new TaskPlannerService(dataDir, null));
        inbox = new CommandInboxService(dataDir, repo, humanQueue);

        // 任务池三桶：accepting / await_plan_approval / blocked
        repo.save("t-acc", Map.of("task_id", "t-acc", "summary", "待终验任务", "updated_at", "2026-10-27T02:00:00Z",
                "fsm", Map.of("state", "accepting")));
        repo.save("t-plan", Map.of("task_id", "t-plan", "summary", "待批任务", "updated_at", "2026-10-27T01:00:00Z",
                "fsm", Map.of("state", "created", "substate", "await_plan_approval")));
        repo.save("t-blk", Map.of("task_id", "t-blk", "summary", "阻塞任务", "updated_at", "2026-10-27T03:00:00Z",
                "fsm", Map.of("state", "blocked")));

        // human-queue：一条与 mp 重复（t-plan plan_approval）、一条独立
        humanQueue.enqueue(Map.of("type", "plan_approval", "status", "pending",
                "title", "批准任务计划 · t-plan", "task_id", "t-plan"));
        humanQueue.enqueue(Map.of("type", "final_acceptance", "status", "pending",
                "title", "终验 · t-other", "task_id", "t-other"));

        // alerts
        Files.writeString(dataDir.resolve("alerts.json"), """
                {"alerts": [{"id":"a1","severity":"warn","message":"负载偏高","ts":"2026-10-27T01:00:00Z"},
                            {"id":"a2","severity":"critical","message":"连续失败","ts":"2026-10-27T02:00:00Z"}]}
                """);

        // 子言 inbox：1 未读 + 1 终态
        Files.writeString(dataDir.resolve("inbox/ziyan/inbox.json"), """
                {"agent": "ziyan", "has_unread": true, "messages": [
                  {"id": "m1", "from": "mailbus", "state": "done", "content": "已处理", "created_at": "2026-10-27T01:00:00Z"},
                  {"id": "m2", "from": "agentA", "state": "pending", "content": "需要你确认方案", "created_at": "2026-10-27T02:00:00Z"}]}
                """);
    }

    @Test
    void draftEmptyIntent400() {
        Map<String, Object> out = draft.draft("  ", "custom", "M");
        assertEquals(400, ((Number) out.get("status")).intValue());
        assertEquals("fatal", ((Map<?, ?>) out.get("body")).get("error"));
    }

    @Test
    void draftTier0ReturnsPlannedChain() {
        Map<String, Object> out = draft.draft("做一个数据面板", "feature", "M");
        assertEquals(200, ((Number) out.get("status")).intValue());
        Map<?, ?> body = (Map<?, ?>) out.get("body");
        assertEquals("ok", body.get("status"));
        Map<?, ?> draftOut = (Map<?, ?>) body.get("draft");
        assertEquals(1, ((List<?>) draftOut.get("planned_chain")).size());
        assertEquals("rules", ((Map<?, ?>) draftOut.get("plan_meta")).get("method"));
    }

    @Test
    void draftUnknownTypeWithoutLlm422() {
        Map<String, Object> out = draft.draft("奇怪需求", "no-such-type", "M");
        assertEquals(422, ((Number) out.get("status")).intValue());
        assertEquals("plan_failed", ((Map<?, ?>) out.get("body")).get("error"));
    }

    @Test
    void draftLlmFailure503() {
        CommandDraftService llmDraft = new CommandDraftService(
                new TaskPlannerService(dataDir, (s, u) -> {
                    throw new TaskPlannerService.LlmError("connection refused");
                }));
        Map<String, Object> out = llmDraft.draft("自由需求", "custom", "M");
        assertEquals(503, ((Number) out.get("status")).intValue());
        assertEquals("llm_error", ((Map<?, ?>) out.get("body")).get("error"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void commandInboxAggregatesFourSourcesWithDedup() {
        Map<String, Object> out = inbox.inbox();
        assertEquals("ok", out.get("status"));
        assertEquals("ziyan", ((Map<String, Object>) out.get("identity")).get("id"));

        List<Map<String, Object>> items = (List<Map<String, Object>>) out.get("items");
        // 3 桶任务 + 1 独立 human-queue（t-plan 的 plan_approval 与 mp 去重）+ 2 告警 + 1 子言未读
        assertEquals(7, items.size());
        assertEquals(7, ((Number) out.get("unread")).intValue());
        assertEquals(1, ((Number) out.get("ziyan_inbox_unread")).intValue());

        long mpCount = items.stream().filter(i -> "manager_pending".equals(i.get("source"))).count();
        assertEquals(3, mpCount);
        long hqCount = items.stream().filter(i -> "human_queue".equals(i.get("source"))).count();
        assertEquals(1, hqCount); // 重复项被去重
        long alertCount = items.stream().filter(i -> "alert".equals(i.get("source"))).count();
        assertEquals(2, alertCount);

        // 动作映射：plan_approval 桶 → approve-plan/rollback
        Map<String, Object> planItem = items.stream()
                .filter(i -> "mp:t-plan:plan_approval".equals(i.get("id"))).findFirst().orElseThrow();
        List<Map<String, Object>> actions = (List<Map<String, Object>>) planItem.get("actions");
        assertEquals("approve-plan", actions.get(0).get("action"));
        assertEquals("批准计划", actions.get(0).get("label"));

        // critical 告警 tone
        Map<String, Object> crit = items.stream()
                .filter(i -> "al:a2".equals(i.get("id"))).findFirst().orElseThrow();
        assertEquals("critical", crit.get("tone"));
    }
}
