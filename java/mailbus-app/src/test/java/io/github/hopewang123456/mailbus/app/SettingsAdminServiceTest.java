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
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 批 A4（2026-10-29）— 设置中心 admin 对等
 * （python config_admin：EDITABLE_SECTIONS/get_section 通用形状/patch 深合并/
 * auth 特化/env 白名单读写/compose 列表）。
 */
class SettingsAdminServiceTest {

    @TempDir
    Path dataDir;

    @TempDir
    Path mailbusRoot;

    private SettingsAdminService admin;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        Files.createDirectories(mailbusRoot);
        admin = new SettingsAdminService(dataDir, mailbusRoot);
        Map<String, Object> cfg = new LinkedHashMap<>();
        cfg.put("agents", Map.of("a1", Map.of("type", "cli")));
        cfg.put("scheduler", Map.of("enabled", true, "tick_seconds", 5, "jobs", List.of()));
        cfg.put("auth", Map.of("allow_write_without_token", false));
        cfg.put("smart_routing", Map.of("l0", "local"));
        JsonFiles.write(dataDir.resolve("config.json"), cfg);
    }

    @Test
    void sectionsMatchesPythonCatalog() {
        List<Map<String, Object>> out = admin.listSections();
        assertEquals(19, out.size());
        assertEquals("agents", out.get(0).get("id")); // sorted
        assertEquals("Agent 运行时", out.get(0).get("label"));
        assertEquals(Boolean.TRUE, out.get(0).get("editable"));
    }

    @Test
    void sectionGetGenericAndSchedulerShape() {
        assertEquals("unknown section: bogus",
                assertThrows(IllegalArgumentException.class, () -> admin.getSection("bogus")).getMessage());

        Map<String, Object> generic = admin.getSection("smart_routing");
        assertEquals("smart_routing", generic.get("section"));
        assertEquals(Map.of("l0", "local"), generic.get("data"));

        Map<String, Object> sched = admin.getSection("scheduler");
        Map<?, ?> data = (Map<?, ?>) sched.get("data");
        assertEquals(5, ((Number) data.get("tick_seconds")).intValue());
        assertTrue(data.containsKey("enabled") && data.containsKey("jobs"));
    }

    @Test
    void sectionPatchDeepMergeAndRestartHints() {
        Map<String, Object> patch = new LinkedHashMap<>();
        patch.put("l1", "cloud");
        patch.put("l0", "local-v2");
        Map<String, Object> out = admin.patchSection("smart_routing", patch);
        assertEquals(List.of("smart_routing"), out.get("requires_restart"));
        // 深合并落盘验证
        Map<String, Object> reread = JsonFiles.readMap(dataDir.resolve("config.json"));
        Map<?, ?> sr = (Map<?, ?>) reread.get("smart_routing");
        assertEquals("cloud", sr.get("l1"));
        assertEquals("local-v2", sr.get("l0"));
    }

    @Test
    void sectionPatchRejectsUnsupportedAndUnknown() {
        assertThrows(UnsupportedOperationException.class, () -> admin.patchSection("agents", Map.of()));
        assertThrows(IllegalArgumentException.class, () -> admin.patchSection("nope", Map.of()));
    }

    @Test
    void authPatchWhitelistAndWideCidrReject() {
        Map<String, Object> patch = Map.of(
                "allow_write_without_token", true,
                "write_without_token_cidrs", List.of("127.0.0.0/8", "10.0.0.0/8"));
        Map<String, Object> out = admin.patchSection("auth", patch);
        assertEquals(List.of("auth"), out.get("requires_restart"));
        Map<?, ?> data = (Map<?, ?>) out.get("data");
        assertEquals(Boolean.TRUE, data.get("allow_write_without_token"));
        assertEquals(List.of("127.0.0.0/8", "10.0.0.0/8"), data.get("write_without_token_cidrs"));

        assertThrows(IllegalArgumentException.class, () -> admin.patchSection("auth",
                Map.of("exempt_cidrs", List.of("0.0.0.0/0"))));
    }

    @Test
    void envStatusGroupsAndSecretMasking() {
        Map<String, Object> out = admin.envStatus();
        Map<?, ?> groups = (Map<?, ?>) out.get("groups");
        assertTrue(groups.containsKey("llm") && groups.containsKey("security"));
        List<?> llm = (List<?>) groups.get("llm");
        assertEquals("MAILBUS_OLLAMA_BASE_URL", ((Map<?, ?>) llm.get(0)).get("key"));
        // secret 键 value 恒 null
        List<?> security = (List<?>) groups.get("security");
        assertEquals(null, ((Map<?, ?>) security.get(0)).get("value"));
        assertEquals(Boolean.TRUE, ((Map<?, ?>) security.get(0)).get("secret"));
    }

    @Test
    void envPatchWhitelistAndFileWrite() throws Exception {
        Map<String, Object> patch = new LinkedHashMap<>();
        patch.put("MAILBUS_OLLAMA_MODEL", "qwen3:4b");
        patch.put("BOGUS_KEY", "x");
        patch.put("CLINE_PROVIDER", "deepseek");
        Map<String, Object> out = admin.patchEnv(patch);
        assertEquals(List.of("MAILBUS_OLLAMA_MODEL", "CLINE_PROVIDER"), out.get("updated"));
        assertEquals(List.of("BOGUS_KEY"), out.get("skipped"));
        // project .env 写入 OLLAMA_MODEL；store .env 写入 CLINE（file=store）
        String rootEnv = Files.readString(mailbusRoot.resolve(".env"));
        assertTrue(rootEnv.contains("MAILBUS_OLLAMA_MODEL=qwen3:4b"));
        String storeEnv = Files.readString(dataDir.resolve(".env"));
        assertTrue(storeEnv.contains("CLINE_PROVIDER=deepseek"));
        // 行替换语义：再写同 key 替换不追加
        admin.patchEnv(Map.of("MAILBUS_OLLAMA_MODEL", "qwen3:8b"));
        rootEnv = Files.readString(mailbusRoot.resolve(".env"));
        assertTrue(rootEnv.contains("qwen3:8b") && !rootEnv.contains("qwen3:4b"));
    }

    @Test
    void deepMergeSemantics() {
        Map<String, Object> base = new LinkedHashMap<>(Map.of("a", Map.of("x", 1, "y", 2), "b", "keep"));
        Map<String, Object> patch = new LinkedHashMap<>(Map.of("a", Map.of("y", 20, "z", 30)));
        Map<String, Object> out = SettingsAdminService.deepMerge(base, patch);
        @SuppressWarnings("unchecked")
        Map<String, Object> a = (Map<String, Object>) out.get("a");
        assertEquals(1, ((Number) a.get("x")).intValue());
        assertEquals(20, ((Number) a.get("y")).intValue());
        assertEquals(30, ((Number) a.get("z")).intValue());
        assertEquals("keep", out.get("b"));
    }

    @Test
    void composeFilesListing() throws Exception {
        Files.createDirectories(mailbusRoot.resolve("docker-agents"));
        Files.writeString(mailbusRoot.resolve("docker-agents/docker-compose.agents.yml"), "x: 1\n");
        Files.writeString(mailbusRoot.resolve("docker-compose.base.yaml"), "x: 2\n");
        List<Map<String, Object>> out = admin.listComposeFiles();
        assertEquals(2, out.size());
        assertTrue(out.stream().anyMatch(i -> "docker-agents/docker-compose.agents.yml".equals(i.get("path"))));
        assertTrue(out.stream().anyMatch(i -> "docker-compose.base.yaml".equals(i.get("path"))));
    }
}
