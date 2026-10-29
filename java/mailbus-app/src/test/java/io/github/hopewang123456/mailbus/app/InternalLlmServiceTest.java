package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * java 机制深化批二（2026-10-30）— Internal LLM 面板对等
 * （python probe.py probe_all / index.py rebuild_index）。
 */
class InternalLlmServiceTest {

    @TempDir
    Path dataDir;

    private InternalLlmService svc;

    @BeforeEach
    void setUp() throws Exception {
        Files.createDirectories(dataDir);
        svc = new InternalLlmService(dataDir);
    }

    private void writeLlmCfg(Map<String, Object> llm) throws Exception {
        JsonFiles.write(dataDir.resolve("config.json"), Map.of("mailbus_internal_llm", llm));
    }

    @Test
    void stubProviderProbeAndActiveSelection() throws Exception {
        writeLlmCfg(Map.of(
                "enabled", true,
                "provider_priority", List.of("stub"),
                "providers", Map.of("stub", Map.of("kind", "stub"))));
        var out = svc.probeAll();
        assertEquals(Boolean.TRUE, out.get("enabled"));
        assertEquals("stub", out.get("active_provider"));
        assertEquals(Boolean.TRUE, out.get("ready"));
        assertEquals("custom", out.get("fallback_mode")); // 非 local 开头
        List<?> providers = (List<?>) out.get("providers");
        assertEquals(1, providers.size());
        assertEquals(Boolean.TRUE, ((Map<?, ?>) providers.get(0)).get("ok"));
    }

    @Test
    void localFirstFallbackMode() throws Exception {
        writeLlmCfg(Map.of(
                "enabled", true,
                "provider_priority", List.of("local", "remote"),
                "providers", Map.of("local", Map.of("kind", "stub"))));
        var out = svc.probeAll();
        assertEquals("local_first", out.get("fallback_mode"));
    }

    @Test
    void deadProviderKeepsNotReady() throws Exception {
        writeLlmCfg(Map.of(
                "enabled", true,
                "provider_priority", List.of("ollama1"),
                "providers", Map.of("ollama1", Map.of(
                        "kind", "ollama", "base_url", "http://127.0.0.1:1", "timeout_seconds", 1))));
        var out = svc.probeAll();
        assertEquals(null, out.get("active_provider"));
        assertEquals(Boolean.FALSE, out.get("ready"));
        List<?> providers = (List<?>) out.get("providers");
        assertEquals(Boolean.FALSE, ((Map<?, ?>) providers.get(0)).get("ok"));
    }

    @Test
    void unknownKindReportsError() {
        var out = svc.probeProvider("weird", Map.of("kind", "quantum"));
        assertEquals(Boolean.FALSE, out.get("ok"));
        assertTrue(String.valueOf(out.get("error")).contains("unknown kind"));
    }

    @Test
    void ragInfoCountsChunks() throws Exception {
        Path mailRoot = dataDir.getParent();
        Path ragDir = mailRoot.resolve("store/rag");
        Files.createDirectories(ragDir);
        JsonFiles.write(ragDir.resolve("mailbus-planner.chunks.json"),
                Map.of("chunks", List.of(Map.of("t", 1), Map.of("t", 2), Map.of("t", 3))));
        var out = svc.ragInfo(Map.of());
        assertEquals(3, ((Number) out.get("chunks")).intValue());
        assertEquals(Boolean.TRUE, out.get("enabled"));
    }

    @Test
    void rebuildIndexFromSources() throws Exception {
        // 源目录：mailRoot/docs-src 两文件
        Path mailRoot = dataDir.getParent();
        Path src = mailRoot.resolve("docs-src");
        Files.createDirectories(src);
        Files.writeString(src.resolve("a.md"), "x".repeat(900)); // 800 截 → 2 块
        Files.writeString(src.resolve("b.md"), "y".repeat(300)); // 1 块
        writeLlmCfg(Map.of("rag", Map.of(
                "sources", List.of(Map.of("id", "docs", "path", "docs-src", "glob", "**/*.md")),
                "max_chars_per_chunk", 800)));
        int n = svc.rebuildIndex();
        assertEquals(3, n);
        // 落盘可读回
        Path index = mailRoot.resolve("store/rag/mailbus-planner.chunks.json");
        Map<String, Object> doc = JsonFiles.readMap(index);
        assertEquals(3, ((List<?>) doc.get("chunks")).size());
        // ragInfo 读回一致
        assertEquals(3, ((Number) svc.ragInfo(Map.of()).get("chunks")).intValue());
    }

    @Test
    void disabledFlagHonored() throws Exception {
        writeLlmCfg(Map.of("enabled", false, "provider_priority", List.of("stub"),
                "providers", Map.of("stub", Map.of("kind", "stub"))));
        var out = svc.probeAll();
        assertEquals(Boolean.FALSE, out.get("enabled"));
        assertEquals(Boolean.FALSE, out.get("ready"));
        assertFalse(Boolean.TRUE.equals(out.get("ready")));
    }
}
