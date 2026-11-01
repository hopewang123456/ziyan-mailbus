package io.github.hopewang123456.mailbus.app;

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
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * java 机制深化批四（2026-10-30）— task_trace 回放时序对等
 * （python application/ops/task_trace.py）。
 */
class TaskTraceServiceTest {

    @TempDir
    Path dataDir;

    private TaskTraceService svc;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir.resolve("tasks"));
        svc = new TaskTraceService(dataDir, new FileTaskRepository(dataDir));
    }

    @Test
    void unknownTask404() {
        assertThrows(IllegalArgumentException.class, () -> svc.trace("nope"));
    }

    @Test
    void traceShapeAndEventTimeline() {
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("task_id", "t-1");
        task.put("intent", "回放测试任务");
        task.put("status", "success");
        task.put("initiator", "manager");
        task.put("created_at", "2026-10-30T10:00:00+0800");
        task.put("updated_at", "2026-10-30T11:00:00+0800");
        task.put("events", List.of(
                Map.of("action", "fsm:dispatch", "actor", "manager", "ts", "2026-10-30T10:01:00+0800", "note", "首步派发")));
        task.put("chain", List.of(Map.of(
                "step_id", "s1", "to_agent", "agentX", "fsm_state", "completed",
                "started_at", "2026-10-30T10:01:30+0800", "completed_at", "2026-10-30T10:30:00+0800")));
        task.put("acceptance_record", Map.of(
                "decision", "approved", "method", "manual", "reviewer", "ziyan",
                "resolved_at", "2026-10-30T10:45:00+0800"));
        JsonFiles.write(dataDir.resolve("tasks/t-1.json"), task);

        var out = svc.trace("t-1");
        assertEquals("t-1", out.get("task_id"));
        assertEquals("success", out.get("status"));
        assertEquals(1, ((List<?>) out.get("steps")).size());

        List<?> events = (List<?>) out.get("events");
        // created + dispatched(event) + dispatched(chain) + step_done + accepted + terminal = 6+
        assertTrue(events.size() >= 5);
        // 排序：首事件 phase=created，尾事件 phase=terminal
        Map<?, ?> first = (Map<?, ?>) events.get(0);
        Map<?, ?> last = (Map<?, ?>) events.get(events.size() - 1);
        assertEquals("created", first.get("phase"));
        assertEquals("terminal", last.get("phase"));
        // ts 截到 19 字符
        assertTrue(String.valueOf(first.get("ts")).length() == 19);
    }

    @Test
    void emptyEventsStillWorks() {
        JsonFiles.write(dataDir.resolve("tasks/t-2.json"), Map.of(
                "task_id", "t-2", "status", "running", "intent", "空事件",
                "created_at", "2026-10-30T09:00:00+0800"));
        var out = svc.trace("t-2");
        List<?> events = (List<?>) out.get("events");
        assertTrue(events.size() >= 1); // 至少 created + status note
    }

    @Test
    void probeN8nNoUrl() {
        var out = svc.probeN8nWebhook("");
        assertEquals(Boolean.FALSE, out.get("ok"));
        assertTrue(String.valueOf(out.get("error")).contains("未配置"));
    }
}
