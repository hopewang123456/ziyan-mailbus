package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.app.HumanQueueService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A 第一组（2026-10-29）— /api/human-queue 与 /api/manager/pending
 * 双栈形状对等（python handlers_tasks.handle_human_queue / queries.manager.manager_pending）。
 */
class ManagerControllerTest {

    @TempDir
    Path dataDir;

    private ManagerController controller;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("tasks"));
        repo = new FileTaskRepository(dataDir);
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new ManagerController(env, repo);
        // 待批任务（plan_approval 桶）+ 交接单（acceptance 桶）
        writeTask("m-pending", "created", "await_plan_approval", null);
        writeTask("m-accept", "accepting", null, null);
        writeTask("m-done", "succeeded", null, null);
        Files.writeString(dataDir.resolve("human-queue.json"), """
                {"version": "1.0.0", "updated_at": "2026-10-29T10:00:00+08:00",
                 "items": [
                   {"id": "hq-1", "status": "pending", "type": "plan_approval", "task_id": "m-pending"},
                   {"id": "hq-2", "status": "resolved", "type": "plan_approval", "task_id": "m-done"}
                 ]}
                """);
    }

    private void writeTask(String id, String state, String substate, String reason) {
        Map<String, Object> fsm = new java.util.LinkedHashMap<>();
        fsm.put("state", state);
        if (substate != null) {
            fsm.put("substate", substate);
        }
        if (reason != null) {
            fsm.put("reason", reason);
        }
        fsm.put("priority", 10);
        Map<String, Object> task = new java.util.LinkedHashMap<>();
        task.put("task_id", id);
        task.put("intent", "待办 " + id);
        task.put("task_type", "custom");
        task.put("initiator", "manager");
        task.put("tier", "M");
        task.put("status", "running");
        task.put("fsm", fsm);
        task.put("chain", List.of());
        task.put("updated_at", "2026-10-29T09:00:00+08:00");
        io.github.hopewang123456.mailbus.infra.json.JsonFiles.write(
                dataDir.resolve("tasks").resolve(id + ".json"), task);
    }

    @Test
    void humanQueueFiltersPendingByDefault() {
        var resp = controller.humanQueue("pending", "", "", "", 50, 0);
        Map<String, Object> body = resp.getBody();
        assertEquals(200, resp.getStatusCode().value());
        assertEquals("ok", body.get("status"));
        assertEquals(1, ((Number) body.get("total")).intValue());
        List<?> items = (List<?>) body.get("items");
        assertEquals(1, items.size());
        assertEquals("hq-1", ((Map<?, ?>) items.get(0)).get("id"));
        assertEquals("1.0.0", body.get("version"));
    }

    @Test
    void humanQueueStatusFilterAndPaging() {
        var all = controller.humanQueue("", "", "", "", 50, 0).getBody();
        assertEquals(2, ((Number) all.get("total")).intValue());
        var page = controller.humanQueue("", "", "", "", 1, 1).getBody();
        List<?> items = (List<?>) page.get("items");
        assertEquals(1, items.size());
        assertEquals("hq-2", ((Map<?, ?>) items.get(0)).get("id"));
        assertEquals(2, ((Number) page.get("total")).intValue()); // total 是过滤后总数
    }

    @Test
    void humanQueueRejectsNegativePaging() {
        var resp = controller.humanQueue("pending", "", "", "", -1, 0);
        assertEquals(400, resp.getStatusCode().value());
        assertEquals("invalid limit/offset", resp.getBody().get("error"));
    }


    private static Map<?, ?> findItem(List<?> items, String taskId) {
        for (Object o : items) {
            Map<?, ?> m = (Map<?, ?>) o;
            if (taskId.equals(String.valueOf(m.get("task_id")))) {
                return m;
            }
        }
        throw new AssertionError("item not found: " + taskId);
    }

    @Test
    void managerPendingBucketsAndCounts() {
        Map<String, Object> out = controller.managerPending();
        assertEquals(2, ((Number) out.get("total")).intValue());
        Map<?, ?> counts = (Map<?, ?>) out.get("counts");
        assertEquals(1, ((Number) counts.get("plan_approval")).intValue());
        assertEquals(1, ((Number) counts.get("acceptance")).intValue());
        assertEquals(0, ((Number) counts.get("coordination")).intValue());
        List<?> items = (List<?>) out.get("items");
        assertEquals(2, items.size());
        // 按 task_id 定位断言（排序不假设）
        Map<?, ?> pending = findItem(items, "m-pending");
        assertEquals("plan_approval", pending.get("bucket"));
        assertEquals(List.of("approve-plan", "rollback", "cancel", "priority"),
                pending.get("suggested_actions"));
        Map<?, ?> accept = findItem(items, "m-accept");
        assertEquals("acceptance", accept.get("bucket"));
        assertEquals(List.of("accept", "rollback", "cancel"), accept.get("suggested_actions"));
    }

    @Test
    void managerPendingSkipsDoneTasks() {
        Map<String, Object> out = controller.managerPending();
        for (Object o : (List<?>) out.get("items")) {
            assertTrue(!"m-done".equals(String.valueOf(((Map<?, ?>) o).get("task_id"))));
        }
    }

}
