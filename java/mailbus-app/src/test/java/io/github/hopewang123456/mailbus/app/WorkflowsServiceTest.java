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
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 交接③ 工作流模板 registry CRUD — python handlers_workflows 对等
 * （SoT registry.json 双栈共享；save 幂等 created 标记）。
 */
class WorkflowsServiceTest {

    @TempDir
    Path dataDir;

    private WorkflowsService svc;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("workflows"));
        Files.writeString(dataDir.resolve("workflows/registry.json"), """
                {"version": "1.0.0", "defaults": {"unknown_task_type_workflow": "llm_adaptive"},
                 "workflows": {
                   "bugfix_s": {"id": "bugfix_s", "version": "1.0.0",
                     "display": {"zh": "小修"}, "mode": "fixed", "task_types": ["bugfix"],
                     "phases": [{"id": "fix", "display": {"zh": "修复"},
                                 "steps": [{"node_type": "agent", "role_type": 8}]}],
                     "gates": []}}}
                """);
        svc = new WorkflowsService(dataDir, Clock.systemUTC());
    }

    @Test
    @SuppressWarnings("unchecked")
    void listSummaryShapeMatchesPython() {
        Map<String, Object> out = svc.list();
        assertEquals("ok", out.get("status"));
        assertEquals("1.0.0", out.get("version"));
        List<Map<String, Object>> items = (List<Map<String, Object>>) out.get("workflows");
        assertEquals(1, items.size());
        Map<String, Object> item = items.get(0);
        assertEquals("bugfix_s", item.get("id"));
        assertEquals("小修", ((Map<?, ?>) item.get("display")).get("zh"));
        assertEquals(1, ((Number) item.get("phase_count")).intValue());
        assertEquals(0, ((Number) item.get("gate_count")).intValue());
    }

    @Test
    void getReturnsFullAndNull() {
        Map<String, Object> wf = svc.get("bugfix_s");
        assertEquals(List.of("bugfix"), wf.get("task_types"));
        assertNull(svc.get("nope"));
    }

    @Test
    void saveCreatesThenUpdatesWithCreatedFlag() {
        Map<String, Object> wf = new java.util.LinkedHashMap<>();
        wf.put("display", Map.of("zh", "新模板"));
        wf.put("mode", "fixed");
        wf.put("phases", List.of(Map.of("id", "p1", "steps", List.of(Map.of("role_type", 1)))));
        Map<String, Object> created = svc.save("my_flow", wf);
        assertEquals("ok", created.get("status"));
        assertEquals(Boolean.TRUE, created.get("created"));
        assertEquals("my_flow", svc.get("my_flow").get("id")); // id 回填

        Map<String, Object> updated = svc.save("my_flow", wf);
        assertEquals(Boolean.FALSE, updated.get("created"));
        assertTrue(svc.list().get("updated_at") != null); // save_registry 刷 updated_at
    }

    @Test
    void saveRejectsInvalidIdAndMissingWorkflow() {
        assertEquals(400, WorkflowsService.httpOf(svc.save("Bad-ID", Map.of("display", "x"))));
        assertEquals(400, WorkflowsService.httpOf(svc.save("ok_id", null)));
    }

    @Test
    void deleteRemovesAnd404s() {
        assertEquals("ok", svc.delete("bugfix_s").get("status"));
        assertNull(svc.get("bugfix_s"));
        assertEquals(404, WorkflowsService.httpOf(svc.delete("bugfix_s")));
    }
}
