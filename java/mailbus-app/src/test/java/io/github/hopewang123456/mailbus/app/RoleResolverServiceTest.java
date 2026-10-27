package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
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
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2a 派发解析 — pin > 空闲优先 > round-robin（python role_resolver 对等）。
 */
class RoleResolverServiceTest {

    @TempDir
    Path dataDir;

    private RoleResolverService resolver;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {"1": {"key": "designer", "display": {"zh": "方案设计师"},
                                  "candidates": ["agentA", "agentB"]}}}
                """);
        Files.writeString(dataDir.resolve("config.json"), """
                {"agents": {"agentA": {"concurrency": 1}, "agentB": {"concurrency": 1}}}
                """);
        Files.createDirectories(dataDir.resolve("inbox/agentA"));
        Files.createDirectories(dataDir.resolve("inbox/agentB"));
        resolver = new RoleResolverService(dataDir, new FileTaskRepository(dataDir));
    }

    private void busyTask(String agent) throws IOException {
        Files.createDirectories(dataDir.resolve("tasks"));
        Files.writeString(dataDir.resolve("tasks/task-busy-" + agent + ".json"), """
                {"task_id": "task-busy-%s", "created_at": "2026-10-27T00:00:00Z",
                 "chain": [{"step": 1, "step_id": "s1", "to_agent": "%s",
                            "to_person": "%s", "fsm_state": "dispatched", "status": "running"}]}
                """.formatted(agent, agent, agent));
    }

    @Test
    void pinWinsWhenDispatchable() {
        RoleResolverService.Resolved r = resolver.resolve(1, "agentB");
        assertEquals("agentB", r.agent());
        assertEquals("pin", r.meta().get("source"));
    }

    @Test
    void idleFirstSkipsBusyCandidate() throws IOException {
        busyTask("agentA");
        RoleResolverService.Resolved r = resolver.resolve(1, null);
        assertEquals("agentB", r.agent());
        assertEquals("idle_first", r.meta().get("source"));
        assertEquals(List.of("agentA"), r.meta().get("skipped_busy"));
    }

    @Test
    void roundRobinWhenAllBusyAndCursorPersists() throws IOException {
        busyTask("agentA");
        busyTask("agentB");
        RoleResolverService.Resolved r1 = resolver.resolve(1, null);
        assertEquals("round_robin", r1.meta().get("source"));
        assertEquals(0, r1.meta().get("index"));
        Map<String, Object> cursor = JsonFiles.readMap(dataDir.resolve("dispatch/role-round-robin.json"));
        assertEquals(1L, ((Number) ((Map<?, ?>) cursor.get("cursors")).get("1")).longValue());

        RoleResolverService.Resolved r2 = resolver.resolve(1, null);
        assertEquals("agentB", r2.agent()); // 游标推进到第二个候选
    }

    @Test
    void unavailableAgentExcludedFallsToNext() throws IOException {
        Files.writeString(dataDir.resolve("config.json"), """
                {"agents": {"agentA": {"available": false}, "agentB": {}}}
                """);
        RoleResolverService.Resolved r = resolver.resolve(1, null);
        assertEquals("agentB", r.agent());
    }

    @Test
    void positionCatalogBusyBecomesRealValue() throws IOException {
        busyTask("agentA");
        PositionCatalogService catalog = new PositionCatalogService(dataDir, resolver);
        Map<String, Object> out = catalog.catalog();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> positions = (List<Map<String, Object>>) out.get("positions");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> candidates = (List<Map<String, Object>>) positions.get(0).get("candidates");
        Map<String, Object> a = candidates.get(0);
        Map<String, Object> b = candidates.get(1);
        assertTrue((Boolean) a.get("busy"));
        assertEquals(1, ((Number) a.get("active_tasks")).intValue());
        assertEquals(false, b.get("busy"));
    }
}
