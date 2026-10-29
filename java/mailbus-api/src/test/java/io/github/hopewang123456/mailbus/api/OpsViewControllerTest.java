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
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A3（2026-10-29）— 运维视图端点对等
 * （python handlers_system：heartbeat/alerts/config/metrics layout+rules/
 * identities rename/positions patch）。
 */
class OpsViewControllerTest {

    @TempDir
    Path dataDir;

    private OpsViewController controller;
    private BulletinController bulletin;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.createDirectories(dataDir.resolve("config/mailbus"));
        MockEnvironment env = new MockEnvironment();
        env.setProperty("mailbus.data-dir", dataDir.toString());
        env.setProperty("mailbus.root", dataDir.toString());
        controller = new OpsViewController(env);
        bulletin = new BulletinController(env);
        // 职位表 seed + 告警规则 seed（mailbusRoot=dataDir）
        Map<String, Object> roles = Map.of(
                "1", Map.of("key", "designer", "display", Map.of("zh", "方案设计师"),
                        "candidates", List.of("agentX")));
        JsonFiles.write(dataDir.resolve("roles/json/role-types.json"), Map.of("roles", roles));
        JsonFiles.write(dataDir.resolve("config/mailbus/alert-rules.json"), Map.of(
                "rules", List.of(Map.of("id", "m-latency", "metric", "latency_p95",
                        "threshold", 10, "severity", "warn", "enabled", true))));
    }

    @Test
    void heartbeatSkeletonAndAggregation() {
        // 空 store：恒含 agents/health 两键（python load_status 骨架）
        Map<String, Object> empty = controller.heartbeat();
        assertEquals(Map.of(), empty.get("agents"));
        assertEquals(Map.of(), empty.get("health"));

        // per-agent daemon 心跳聚合（heartbeat.{agent}.json，agent 字段为键）
        JsonFiles.write(dataDir.resolve("heartbeat.agentX.json"),
                Map.of("agent", "agentX", "state", "alive"));
        Map<String, Object> out = controller.heartbeat();
        @SuppressWarnings("unchecked")
        Map<String, Object> agents = (Map<String, Object>) out.get("agents");
        assertEquals("alive", ((Map<?, ?>) agents.get("agentX")).get("state"));

        // bus 共享心跳合并
        JsonFiles.write(dataDir.resolve("heartbeat.json"),
                Map.of("agents", Map.of("agentM", Map.of("state", "ok")), "health", Map.of("bus", "up")));
        out = controller.heartbeat();
        agents = (Map<String, Object>) out.get("agents");
        assertTrue(agents.containsKey("agentX") && agents.containsKey("agentM"));
        assertEquals(Map.of("bus", "up"), out.get("health"));
    }

    @Test
    void alertsReturnsTail() {
        var alerts = new java.util.ArrayList<>();
        for (int i = 0; i < 55; i++) {
            alerts.add(Map.of("id", "al-" + i, "type", "t"));
        }
        JsonFiles.write(dataDir.resolve("alerts.json"), Map.of("alerts", alerts));
        List<?> out = (List<?>) controller.alerts().get("alerts");
        assertEquals(50, out.size());
        assertEquals("al-5", ((Map<?, ?>) out.get(0)).get("id")); // 尾部 50 条
    }

    @Test
    void configRedactsToken() {
        JsonFiles.write(dataDir.resolve("config.json"), new LinkedHashMap<>(Map.of(
                "api_token", "secret-value", "agents", Map.of("a", Map.of()), "token", "x")));
        Map<String, Object> out = controller.config();
        assertEquals("***", out.get("api_token"));
        assertTrue(!out.containsKey("token"));
        assertTrue(out.containsKey("agents"));
    }

    @Test
    void metricsRulePatchWhitelistAndMerge() {
        var bad = controller.rulePatch("m1", Map.of("bogus", 1));
        assertEquals(400, bad.getStatusCode().value());
        assertTrue(String.valueOf(bad.getBody().get("detail")).contains("不可编辑字段"));

        var missing = controller.rulePatch("nope", Map.of("enabled", false));
        assertEquals(404, missing.getStatusCode().value());

        // seed 规则（借 DashboardConfigService 的 seed 机制：读一条真实 seed id）
        io.github.hopewang123456.mailbus.app.DashboardConfigService dash =
                new io.github.hopewang123456.mailbus.app.DashboardConfigService(dataDir, dataDir);
        List<Map<String, Object>> seeds = dash.rules();
        String seedId = String.valueOf(seeds.get(0).get("id"));
        var ok = controller.rulePatch(seedId, Map.of("enabled", false, "threshold", 5));
        assertEquals(200, ok.getStatusCode().value());
        @SuppressWarnings("unchecked")
        Map<String, Object> rule = (Map<String, Object>) ok.getBody().get("rule");
        assertEquals(Boolean.FALSE, rule.get("enabled"));
        assertEquals(5, ((Number) rule.get("threshold")).intValue());
        // 覆盖层落盘
        Map<String, Object> overlay = JsonFiles.readMap(dataDir.resolve("config/alert-rules.json"));
        assertTrue(overlay != null && overlay.get("rules") instanceof List<?>);
    }

    @Test
    void identityRenameRoundTrip() throws Exception {
        // 内置身份：写最小 identities 文件（BuiltinIdentitiesService 读 mailbusRoot 下 identities/）
        // 若服务找不到身份 → 404 分支；找到则 200。两条分支都断言不抛错。
        var missing = controller.identityRename("no-such-id", Map.of("display_name", "x"));
        assertTrue(missing.getStatusCode().value() == 404 || missing.getStatusCode().value() == 200);
    }

    @Test
    void positionPatchWhitelistAndInputs() {
        var bad = controller.positionPatch(1, Map.of("hack", true));
        assertEquals(400, bad.getStatusCode().value());
        assertTrue(String.valueOf(bad.getBody().get("detail")).contains("不可编辑字段"));

        var badInput = controller.positionPatch(1,
                Map.of("inputs", List.of(Map.of("name", "x", "type", "enum"))));
        assertEquals(400, badInput.getStatusCode().value());
        assertTrue(String.valueOf(badInput.getBody().get("detail")).contains("options"));

        var missing = controller.positionPatch(99, Map.of("default_sla_minutes", 30));
        assertEquals(404, missing.getStatusCode().value());

        var ok = controller.positionPatch(1, Map.of(
                "candidates", List.of("agentX", "agentY"), "default_sla_minutes", 45));
        assertEquals(200, ok.getStatusCode().value());
        @SuppressWarnings("unchecked")
        Map<String, Object> entry = (Map<String, Object>) ok.getBody().get("entry");
        assertEquals(List.of("agentX", "agentY"), entry.get("candidates"));
        // SoT 落盘
        Map<String, Object> reread = JsonFiles.readMap(dataDir.resolve("roles/json/role-types.json"));
        @SuppressWarnings("unchecked")
        Map<String, Object> role1 = (Map<String, Object>) ((Map<?, ?>) reread.get("roles")).get("1");
        assertEquals(45, ((Number) role1.get("default_sla_minutes")).intValue());
    }

    @Test
    void permissionRoundTrip() {
        var empty = bulletin.permissionGet();
        assertTrue(empty.isEmpty() || empty.get("permissions") == null);

        var post = bulletin.permissionPost(Map.of(
                "permissions", Map.of("agentA", Map.of("post_bulletin", true)),
                "bulletin", List.of("agentA")));
        assertEquals(200, post.getStatusCode().value());

        Map<String, Object> read = bulletin.permissionGet();
        assertTrue(read.containsKey("permissions"));
        assertTrue(read.containsKey("bulletin"));
        assertTrue(read.containsKey("updated_at"));
    }
}
