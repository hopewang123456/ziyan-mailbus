package io.github.hopewang123456.mailbus.app;

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
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * java 机制深化批三（2026-10-30）— clinic/agent 生命周期对等
 * （python scheduler._hub_state / list_active_agents 三级门禁）。
 */
class ClinicAgentServiceTest {

    @TempDir
    Path dataDir;

    private ClinicAgentService svc;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        svc = new ClinicAgentService(dataDir);
    }

    @Test
    void clinicToolsShape() {
        var tools = svc.clinicTools();
        assertEquals(10, tools.size());
        Map<?, ?> first = tools.get(0);
        assertEquals("check-token-status", first.get("id"));
        assertTrue(String.valueOf(first.get("script")).startsWith("tools/clinic/"));
    }

    @Test
    void schedulerStatusShape() throws Exception {
        JsonFiles.write(dataDir.resolve("scheduler-state.json"), Map.of(
                "jobs", Map.of("scan", Map.of("last_rc", 0, "last_elapsed_s", 1.2))));
        var out = svc.schedulerStatus(true);
        assertEquals(Boolean.TRUE, out.get("running"));
        assertTrue(out.containsKey("started_at"));
        Map<?, ?> jobs = (Map<?, ?>) out.get("jobs");
        assertTrue(jobs.containsKey("scan"));
    }

    @Test
    void activeAgentsThreeGates() throws Exception {
        Map<String, Object> agents = new LinkedHashMap<>();
        agents.put("a-on", Map.of("type", "cli", "enabled", true));                    // 通过
        agents.put("a-retired", Map.of("type", "cli", "enabled", false));               // 门1 角色退役
        agents.put("a-inst-off", Map.of("type", "cli", "instance_id", "i2"));          // 门2 实例关
        agents.put("a-fw-off", Map.of("type", "hermes"));                               // 门3 框架关
        agents.put("a-fw-on", Map.of("type", "codex", "framework", "codex"));           // 通过
        JsonFiles.write(dataDir.resolve("config.json"), Map.of(
                "agents", agents,
                "agent_instances", Map.of("i2", Map.of("enabled", false)),
                "frameworks", Map.of("hermes", Map.of("enabled", false), "codex", Map.of("enabled", true))));
        var out = svc.activeAgents();
        assertEquals(2, out.size()); // a-on + a-fw-on（a-inst-off 被实例门拦）
        assertTrue(out.containsKey("a-on") && out.containsKey("a-fw-on"));
        assertFalse(out.containsKey("a-retired"));
        assertFalse(out.containsKey("a-inst-off"));
        assertFalse(out.containsKey("a-fw-off"));
    }

    @Test
    void assemblySkeleton() throws Exception {
        JsonFiles.write(dataDir.resolve("config.json"),
                Map.of("agents", Map.of("x", Map.of("type", "cli"))));
        var out = svc.agentsAssembly();
        assertEquals(1, out.size());
        assertEquals("cli", ((Map<?, ?>) out.get("x")).get("type"));
    }
}
