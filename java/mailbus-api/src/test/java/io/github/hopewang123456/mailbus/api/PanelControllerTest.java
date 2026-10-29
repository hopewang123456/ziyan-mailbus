package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A6 第一组（2026-10-29）— 面板读型五端点对等
 * （python handlers_system：templates/reports/patrol-reports/workload/tokens-summary）。
 */
class PanelControllerTest {

    @TempDir
    Path dataDir;

    private PanelController controller;

    @BeforeEach
    void setUp() throws Exception {
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new PanelController(env, new FileTaskRepository(dataDir));
    }

    @Test
    void templatesFromConfig() throws Exception {
        assertEquals(Map.of(), controller.templates());
        JsonFiles.write(dataDir.resolve("config.json"),
                Map.of("agent_types", Map.of("models", Map.of("tier_m", "x"))));
        assertEquals(Map.of("tier_m", "x"),
                ((Map<?, ?>) controller.templates()).get("models"));
    }

    @Test
    void reportsTail7FilesWithRecentEntries() throws Exception {
        Files.createDirectories(dataDir.resolve("errors"));
        for (int i = 1; i <= 3; i++) {
            StringBuilder sb = new StringBuilder();
            for (int j = 1; j <= 3; j++) {
                sb.append("{\"code\": \"e-").append(i).append("-").append(j).append("\"}\n");
            }
            Files.writeString(dataDir.resolve("errors/day-" + i + ".jsonl"), sb.toString());
        }
        var out = controller.reports();
        List<?> reports = (List<?>) out.get("reports");
        assertEquals(3, reports.size());
        // 排序倒序（文件名 desc）
        Map<?, ?> first = (Map<?, ?>) reports.get(0);
        assertEquals("day-3.jsonl", first.get("file"));
        assertEquals(3, ((Number) first.get("count")).intValue());
        assertEquals(3, ((List<?>) first.get("recent")).size());
    }

    @Test
    void patrolReportsTailWithSummary() throws Exception {
        Files.createDirectories(dataDir.resolve("patrol_reports"));
        Files.writeString(dataDir.resolve("patrol_reports/2026-10-29.md"), "巡检正常".repeat(50));
        var out = controller.patrolReports();
        List<?> reports = (List<?>) out.get("reports");
        assertEquals(1, reports.size());
        Map<?, ?> r = (Map<?, ?>) reports.get(0);
        assertEquals("2026-10-29.md", r.get("file"));
        assertTrue(String.valueOf(r.get("summary")).startsWith("巡检正常"));
        assertEquals(200, String.valueOf(r.get("summary")).length()); // 内容 200 字<300 → 全量
        assertEquals(200, String.valueOf(r.get("content")).length()); // 同上 <500
    }

    @Test
    void emptyDirsGiveEmptyLists() {
        assertEquals(Map.of("reports", List.of()), controller.reports());
        assertEquals(Map.of("reports", List.of()), controller.patrolReports());
    }

    @Test
    void workloadAggregates() throws Exception {
        Files.createDirectories(dataDir.resolve("tasks"));
        JsonFiles.write(dataDir.resolve("tasks/t-1.json"), Map.of(
                "task_id", "t-1", "status", "running", "assignee", "agentX",
                "chain", List.of(Map.of("step_id", "s1", "fsm_state", "queued", "to_agent", "agentX"))));
        JsonFiles.write(dataDir.resolve("config.json"),
                Map.of("agents", Map.of("agentX", Map.of("name", "子言", "role", "manager"))));
        var out = controller.workload();
        Map<?, ?> agents = (Map<?, ?>) out.get("agents");
        Map<?, ?> ax = (Map<?, ?>) agents.get("agentX");
        assertEquals("子言", ax.get("name"));
        assertEquals(1, ((Number) ax.get("active_tasks")).intValue());
        assertEquals(1, ((Number) ax.get("queued_steps")).intValue());
        assertTrue(((String) out.get("generated_at")).matches("\\d{4}-\\d{2}-\\d{2}T.*"));
    }

    @Test
    void tokenSummaryAggregatesLedger() throws Exception {
        Files.createDirectories(dataDir.resolve("ledger"));
        String today = java.time.LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"))
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd"));
        Files.writeString(dataDir.resolve("ledger/tokens-" + today + ".jsonl"), """
                {"est_tokens": 100, "agent": "agentX", "task_id": "t-1", "kind": "llm", "ts": "2026-10-29T10:00:00+0800"}
                {"est_tokens": 50, "agent": "agentY", "task_id": "", "kind": "llm", "ts": "2026-10-29T10:01:00+0800"}
                not-json-line
                """);
        JsonFiles.write(dataDir.resolve("config.json"),
                Map.of("mailbus_automation", Map.of("token_budget", Map.of("daily_est_tokens", 1000))));
        var out = controller.tokenSummary();
        assertEquals("ok", out.get("status"));
        assertEquals(2, ((Number) out.get("calls")).intValue());
        assertEquals(150, ((Number) out.get("est_tokens_total")).intValue());
        assertEquals(100, ((Map<?, ?>) out.get("by_agent")).get("agentX"));
        List<?> top = (List<?>) out.get("top_tasks");
        assertEquals("t-1", ((Map<?, ?>) top.get(0)).get("task_id"));
        Map<?, ?> budget = (Map<?, ?>) out.get("budget");
        assertEquals(1000, ((Number) budget.get("daily_est_tokens")).intValue());
        assertEquals(Boolean.FALSE, budget.get("exceeded"));
        assertEquals(15.0, ((Number) budget.get("used_pct")).doubleValue(), 0.01);
        Map<?, ?> peak = (Map<?, ?>) out.get("peak");
        assertEquals("2026-10-29T10:00", peak.get("minute"));
        assertEquals(100, ((Number) peak.get("est_tokens")).intValue());
    }

    @Test
    void tokenSummaryEmptyDay() {
        var out = controller.tokenSummary();
        assertEquals(0, ((Number) out.get("calls")).intValue());
        assertEquals(Map.of(), out.get("by_agent"));
    }
}
