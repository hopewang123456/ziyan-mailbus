package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * java 机制深化批五（2026-10-30）— workflow gates engine 对等
 * （python engine.py on_gate_approve / on_gate_deny 核心语义）。
 */
class GateEngineServiceTest {

    @TempDir
    Path dataDir;

    private GateEngineService svc;
    private FileTaskRepository repo;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        Files.createDirectories(dataDir.resolve("roles/json"));
        repo = new FileTaskRepository(dataDir);
        Clock clock = Clock.systemDefaultZone();
        svc = new GateEngineService(dataDir, repo,
                new HumanQueueService(dataDir, clock),
                new StepDispatcher(dataDir, clock));
        // 最小 workflow registry：一个 workflow 一个门
        Files.writeString(dataDir.resolve("workflow-registry.json"), """
                {"workflows": {"wf-demo": {
                  "id": "wf-demo",
                  "gates": [
                    {"gate_id": "review", "required_inputs": [],
                     "on_approve": {"action": "append_phase", "phase_id": "p2"},
                     "on_deny": {"action": "rollback_phase", "rollback_phase_id": "p1"}}
                  ],
                  "phases": [
                    {"id": "p1", "role_types": [1]},
                    {"id": "p2", "role_types": [8]}
                  ]
                }}}
                """);
    }

    private void writeTask(String id, String... gatesStatus) {
        Map<String, Object> ext = new LinkedHashMap<>();
        Map<String, Object> mailbus = new LinkedHashMap<>();
        mailbus.put("workflow_id", "wf-demo");
        var gates = new java.util.ArrayList<Map<String, Object>>();
        for (int i = 0; i < gatesStatus.length; i += 2) {
            gates.add(Map.of("gate_id", gatesStatus[i], "status", gatesStatus[i + 1]));
        }
        mailbus.put("gates", gates);
        ext.put("mailbus", mailbus);

        Map<String, Object> task = new LinkedHashMap<>();
        task.put("task_id", id);
        task.put("intent", "门禁测试");
        task.put("status", "running");
        task.put("fsm", Map.of("state", "executing"));
        task.put("extensions", ext);
        task.put("chain", List.of(Map.of("step_id", "s1", "role_type", 1, "fsm_state", "completed")));
        JsonFiles.write(dataDir.resolve("tasks").resolve(id + ".json"), task);
    }

    @Test
    void approveUnknownTask() {
        var out = svc.approve("nope", "review", Map.of());
        assertFalse((Boolean) out.get("ok"));
        assertEquals(404, ((Number) out.get("http")).intValue());
    }

    @Test
    void approveUnknownGate() {
        writeTask("t-1");
        var out = svc.approve("t-1", "bogus", Map.of());
        assertFalse((Boolean) out.get("ok"));
        assertEquals(404, ((Number) out.get("http")).intValue());
    }

    @Test
    void approveHappyPath() {
        writeTask("t-ok");
        var out = svc.approve("t-ok", "review", Map.of("reviewer", "ziyan"));
        assertTrue((Boolean) out.get("ok"), String.valueOf(out));
        assertEquals("review", out.get("gate_id"));
        Map<?, ?> resolution = (Map<?, ?>) out.get("resolution");
        assertEquals("approved", resolution.get("decision"));
        assertEquals("ziyan", resolution.get("reviewer"));
        // 实例落盘验证
        Map<String, Object> saved = repo.find("t-ok").orElseThrow();
        Map<?, ?> mb = (Map<?, ?>) ((Map<?, ?>) saved.get("extensions")).get("mailbus");
        List<?> gates = (List<?>) mb.get("gates");
        assertEquals("approved", ((Map<?, ?>) gates.get(0)).get("status"));
        // on_approve append_phase → chain 追加了 s2（role_type=8）
        List<?> chain = (List<?>) saved.get("chain");
        assertEquals(2, chain.size());
        // FSM → executing + status running
        assertEquals("running", saved.get("status"));
    }

    @Test
    void approveAlreadyApproved() {
        writeTask("t-dup", "review", "approved");
        var out = svc.approve("t-dup", "review", Map.of());
        assertFalse((Boolean) out.get("ok"));
        assertEquals("gate_not_pending", out.get("error"));
    }

    @Test
    void denyHappyPath() {
        writeTask("t-deny");
        var out = svc.deny("t-deny", "review", Map.of("reason", "质量不达标"));
        assertTrue((Boolean) out.get("ok"), String.valueOf(out));
        Map<?, ?> resolution = (Map<?, ?>) out.get("resolution");
        assertEquals("denied", resolution.get("decision"));
        assertEquals("质量不达标", resolution.get("reason"));
        // 实例 denied 落盘
        Map<String, Object> saved = repo.find("t-deny").orElseThrow();
        Map<?, ?> mb = (Map<?, ?>) ((Map<?, ?>) saved.get("extensions")).get("mailbus");
        List<?> gates = (List<?>) mb.get("gates");
        assertEquals("denied", ((Map<?, ?>) gates.get(0)).get("status"));
    }

    @Test
    void denyWithoutReason() {
        writeTask("t-nr");
        var out = svc.deny("t-nr", "review", Map.of());
        assertFalse((Boolean) out.get("ok"));
        assertEquals("reason required for deny", out.get("error"));
    }
}
