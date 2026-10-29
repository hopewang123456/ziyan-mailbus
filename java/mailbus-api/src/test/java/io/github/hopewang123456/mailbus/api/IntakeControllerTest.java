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
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * 批 A5（2026-10-29）— intake 三 GET 端点对等
 * （python handlers_intake：list/get/tasks；存储 leads/order-intake.json）。
 */
class IntakeControllerTest {

    @TempDir
    Path dataDir;

    private IntakeController controller;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        Files.createDirectories(dataDir.resolve("tasks"));
        repo = new FileTaskRepository(dataDir);
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new IntakeController(env, repo);
    }

    private void writeIntakes(String json) throws Exception {
        Files.createDirectories(dataDir.resolve("leads"));
        Files.writeString(dataDir.resolve("leads/order-intake.json"), json);
    }

    @Test
    void listShape() throws Exception {
        writeIntakes("""
                [{"intake_id": "in-1", "title": "线索A"},
                 {"intake_id": "in-2", "title": "线索B"}]
                """);
        var out = controller.list();
        assertEquals("ok", out.get("status"));
        assertEquals(2, ((Number) out.get("count")).intValue());
        assertEquals(2, ((List<?>) out.get("intakes")).size());
    }

    @Test
    void emptyListDefaults() {
        var out = controller.list(); // 无文件
        assertEquals(0, ((Number) out.get("count")).intValue());
        assertEquals(List.of(), out.get("intakes"));
    }

    @Test
    void getHitAndMiss() throws Exception {
        writeIntakes("""
                [{"intake_id": "in-1", "title": "线索A"}]
                """);
        assertEquals("ok", controller.get("in-1").getBody().get("status"));
        assertEquals(404, controller.get("nope").getStatusCode().value());
        assertEquals("not_found", controller.get("nope").getBody().get("error"));
    }

    @Test
    void tasksFollowsPipelineLink() throws Exception {
        writeIntakes("""
                [{"intake_id": "in-1", "pipeline_link": {"intake_task_id": "t-1", "solution_task_id": "t-2"}}]
                """);
        JsonFiles.write(dataDir.resolve("tasks/t-1.json"),
                Map.of("task_id", "t-1", "status", "success"));
        var out = controller.tasks("in-1").getBody();
        assertEquals("ok", out.get("status"));
        List<?> tasks = (List<?>) out.get("tasks");
        assertEquals(1, tasks.size()); // t-2 不存在 → 只回 t-1
        Map<?, ?> item = (Map<?, ?>) tasks.get(0);
        assertEquals("intake_task_id", item.get("link_key"));
        assertEquals("t-1", item.get("task_id"));

        assertEquals(404, controller.tasks("nope").getStatusCode().value());
    }

    @Test
    void spawnFamilyReturns501() {
        assertEquals(501, controller.spawn("in-1").getStatusCode().value());
        assertEquals(501, controller.spawnAnalyze().getStatusCode().value());
        assertEquals(501, controller.gateApprove("in-1", "g1").getStatusCode().value());
        assertEquals(501, controller.gateDeny("in-1", "g1").getStatusCode().value());
    }
}
