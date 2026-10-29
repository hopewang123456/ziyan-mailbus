package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.env.MockEnvironment;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A7（2026-10-29）— lifecycle 单条群对等
 * （discover 落盘/align enabled 补齐/agent-profile 显式路径读/骨架族/501）。
 */
class LifecycleControllerTest {

    @TempDir
    Path dataDir;

    private LifecycleController controller;

    @BeforeEach
    void setUp() {
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        controller = new LifecycleController(env);
    }

    @Test
    void discoverSkeletonAndPersist() {
        var out = controller.discover();
        assertEquals(0, ((Number) out.get("count")).intValue());
        assertTrue(Files.isRegularFile(dataDir.resolve("system/discovery-report.json")));
    }

    @Test
    void alignBackfillsEnabledAndCounts() throws Exception {
        Map<String, Object> agents = new LinkedHashMap<>();
        agents.put("a1", new LinkedHashMap<>(Map.of("type", "cli"))); // 无 enabled → 补 false
        agents.put("a2", new LinkedHashMap<>(Map.of("type", "cli", "enabled", true)));
        JsonFiles.write(dataDir.resolve("config.json"), new LinkedHashMap<>(Map.of("agents", agents)));

        var out = controller.alignGet();
        assertEquals(2, ((Number) out.get("agent_count")).intValue());
        assertEquals(13, ((Number) out.get("expect_min")).intValue());
        assertFalse((Boolean) out.get("ok")); // 2 < 13
        assertTrue(String.valueOf(out.get("warning")).contains("expect_min=13"));
        assertEquals(List.of("a1", "a2"), out.get("agent_ids"));
        // enabled 补齐落盘
        Map<String, Object> reread = JsonFiles.readMap(dataDir.resolve("config.json"));
        assertTrue(((Map<?, ?>) ((Map<?, ?>) reread.get("agents")).get("a1")).containsKey("enabled"));
    }

    @Test
    void agentProfileReadsExplicitPaths() throws Exception {
        Path idFile = dataDir.resolve("identity.md");
        Files.writeString(idFile, "# 身份文档");
        Map<String, Object> agentCfg = new LinkedHashMap<>();
        agentCfg.put("type", "cli");
        agentCfg.put("profile_paths", Map.of("identity", idFile.toString()));
        agentCfg.put("skill_groups", List.of("coding", "review"));
        JsonFiles.write(dataDir.resolve("config.json"),
                new LinkedHashMap<>(Map.of("agents", Map.of("agentX", agentCfg))));

        var out = controller.agentProfile("agentX").getBody();
        assertEquals("agentX", out.get("name"));
        assertEquals("# 身份文档", out.get("identity"));
        assertNull(out.get("soul"));
        assertEquals(2, ((List<?>) out.get("skills")).size());
        assertEquals(404, controller.agentProfile("nope").getStatusCode().value());
    }

    @Test
    void searchSkeletonAndPingGuards() throws Exception {
        var search = controller.search("q");
        assertEquals(0, ((Number) search.get("count")).intValue());

        assertEquals(404, controller.ping("nope").getStatusCode().value());
        JsonFiles.write(dataDir.resolve("config.json"),
                Map.of("agents", Map.of("agentX", Map.of("type", "cli"))));
        var ping = controller.ping("agentX").getBody();
        assertEquals(Boolean.FALSE, ping.get("online"));
    }

    @Test
    void doctor501() {
        assertEquals(501, controller.doctor().getStatusCode().value());
    }
}
