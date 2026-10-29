package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A2（2026-10-29）— 任务审计四端点对等
 * （python tracker.audit_stats / audit_trend / handlers_tasks.handle_task_update）。
 */
class TaskAuditControllerTest {

    @TempDir
    Path dataDir;

    private TaskAuditController controller;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir.resolve("tasks"));
        repo = new FileTaskRepository(dataDir);
        controller = new TaskAuditController(null, repo);
    }

    private void writeTask(String id, String status, Map<String, Object> fsm, List<?> auditLog) {
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("task_id", id);
        task.put("summary", "任务 " + id);
        task.put("status", status);
        task.put("tier", "M");
        task.put("fsm", fsm);
        task.put("chain", List.of());
        task.put("updated_at", "2026-10-29T09:00:00+0800");
        if (auditLog != null) {
            task.put("audit_log", auditLog);
        }
        JsonFiles.write(dataDir.resolve("tasks").resolve(id + ".json"), task);
    }

    private static Map<String, Object> entry(String result, String reviewer, String at, String cat) {
        Map<String, Object> e = new LinkedHashMap<>();
        e.put("result", result);
        e.put("reviewer", reviewer);
        e.put("at", at);
        e.put("category", cat);
        e.put("severity", "normal");
        return e;
    }

    @Test
    void auditStatsAggregates() {
        writeTask("t-1", "success", Map.of("state", "succeeded"),
                List.of(entry("pass", "agentC", "2026-10-28T10:00:00+0800", "code_review"),
                        entry("fail", "agentC", "2026-10-29T10:00:00+0800", "design")));
        writeTask("t-2", "success", Map.of("state", "succeeded"),
                List.of(entry("warn", "agentD", "2026-10-29T11:00:00+0800", "code_review")));

        Map<String, Object> out = controller.auditStats();
        assertEquals(2, ((Number) out.get("total_tasks")).intValue());
        assertEquals(2, ((Number) out.get("audited_tasks")).intValue());
        assertEquals(1, ((Number) out.get("pass_count")).intValue());
        assertEquals(1, ((Number) out.get("fail_count")).intValue());
        assertEquals(1, ((Number) out.get("warn_count")).intValue());
        assertEquals(3, ((Number) out.get("total_audit_entries")).intValue());
        assertEquals(33.3, ((Number) out.get("pass_rate")).doubleValue(), 0.05);

        Map<?, ?> byReviewer = (Map<?, ?>) out.get("by_reviewer");
        Map<?, ?> agentC = (Map<?, ?>) byReviewer.get("agentC");
        assertEquals(1, ((Number) agentC.get("pass")).intValue());
        assertEquals(2, ((Number) agentC.get("total")).intValue());
        Map<?, ?> byCategory = (Map<?, ?>) out.get("by_category");
        assertEquals(2, ((Number) byCategory.get("code_review")).intValue());

        // latest_audits 按 at 倒序、截 20
        List<?> latest = (List<?>) out.get("latest_audits");
        assertEquals(3, latest.size());
        assertEquals("agentD", ((Map<?, ?>) latest.get(0)).get("reviewer"));
    }

    @Test
    void auditTrendByDay() {
        writeTask("t-1", "success", Map.of("state", "succeeded"),
                List.of(entry("pass", "a", "2026-10-28T10:00:00+0800", "c1"),
                        entry("pass", "a", "2026-10-28T18:00:00+0800", "c1"),
                        entry("fail", "a", "2026-10-29T09:00:00+0800", "c1")));
        Map<String, Object> out = controller.auditTrend("day", 30);
        List<?> trend = (List<?>) out.get("trend");
        assertEquals(2, trend.size());
        Map<?, ?> d28 = (Map<?, ?>) trend.get(0);
        assertEquals("2026-10-28", d28.get("period"));
        assertEquals(2, ((Number) d28.get("total")).intValue());
        assertEquals(100.0, ((Number) d28.get("pass_rate")).doubleValue(), 0.05);
        Map<?, ?> summary = (Map<?, ?>) out.get("summary");
        assertEquals(3, ((Number) summary.get("total_audits")).intValue());
        assertEquals(66.7, ((Number) summary.get("avg_pass_rate")).doubleValue(), 0.05);
    }

    @Test
    void auditTrendEmptyAndWeekPeriod() {
        Map<String, Object> empty = controller.auditTrend("day", 30);
        assertEquals(List.of(), empty.get("trend"));
        assertEquals(0, ((Number) ((Map<?, ?>) empty.get("summary")).get("total_audits")).intValue());

        writeTask("t-1", "success", Map.of("state", "succeeded"),
                List.of(entry("pass", "a", "2026-10-28T10:00:00+0800", "c1")));
        List<?> week = (List<?>) controller.auditTrend("week", 30).get("trend");
        assertEquals(1, week.size());
        assertTrue(String.valueOf(((Map<?, ?>) week.get(0)).get("period")).contains("-W"));
    }

    @Test
    void auditPendingFiltersNoiseAndNonAudited() {
        // 需要审计但未审：chain 有 step
        Map<String, Object> t = new LinkedHashMap<>();
        t.put("task_id", "t-pending");
        t.put("summary", "正常任务");
        t.put("status", "success");
        t.put("fsm", Map.of("state", "succeeded"));
        t.put("chain", List.of(Map.of("step_id", "s1", "to_agent", "agentX")));
        JsonFiles.write(dataDir.resolve("tasks").resolve("t-pending.json"), t);
        // 噪声前缀：无需审计
        writeTask("msg-noise", "success", Map.of("state", "succeeded"), null);
        writeTask("t-pending2", "running", Map.of("state", "executing"), null);

        Map<String, Object> out = controller.auditPending(50);
        assertEquals(1, ((Number) out.get("count")).intValue());
        assertEquals(50, ((Number) out.get("limit")).intValue());
        List<?> items = (List<?>) out.get("tasks");
        assertEquals("t-pending", ((Map<?, ?>) items.get(0)).get("task_id"));
    }

    @Test
    void updateValidatesAndPersists() {
        var missing = controller.update(Map.of("status", "running"));
        assertEquals(400, missing.getStatusCode().value());
        assertEquals("缺少 task_id", missing.getBody().get("error"));

        var badStatus = controller.update(Map.of("task_id", "t-1", "status", "nope"));
        assertEquals(400, badStatus.getStatusCode().value());
        assertTrue(String.valueOf(badStatus.getBody().get("error")).contains("无效状态"));

        writeTask("t-1", "running", Map.of("state", "executing"), null);
        var ok = controller.update(Map.of("task_id", "t-1", "status", "success"));
        assertEquals(200, ok.getStatusCode().value());
        assertEquals("success", repo.find("t-1").orElseThrow().get("status"));
    }
}
