package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** P2 B1/B2 — java 指标：manifest 同源读取 + 计算器（对等 python 协议与口径）。 */
class MailbusMetricsTest {

    private Path seedRoot(@TempDir Path tmp) throws IOException {
        Path seed = tmp.resolve("config/mailbus");
        Files.createDirectories(seed);
        Files.writeString(seed.resolve("metrics-manifest.json"), """
                {"metrics": [
                  {"id": "bus.messages_total", "source": "messages", "unit": "count"},
                  {"id": "agents.total", "source": "agents", "unit": "count"},
                  {"id": "tasks.active", "source": "tasks", "unit": "count"}
                ]}
                """);
        return tmp;
    }

    @Test
    void manifestReadsSharedSeed(@TempDir Path dataDir) throws IOException {
        Path root = seedRoot(Files.createTempDirectory("seed"));
        MetricsManifestService svc = new MetricsManifestService(dataDir, root);
        List<Map<String, Object>> metrics = svc.metrics();
        assertEquals(3, metrics.size());
        assertEquals("bus.messages_total", metrics.get(0).get("id"));
    }

    @Test
    void calculatorSourcesAndValues(@TempDir Path dataDir) throws IOException {
        Path root = seedRoot(Files.createTempDirectory("seed"));
        MetricsManifestService manifest = new MetricsManifestService(dataDir, root);

        // 端口替身：messages 用 adapters 内存实现；agents 用最小匿名目录
        io.github.hopewang123456.mailbus.ports.MessageRepository messages =
                new io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository();
        io.github.hopewang123456.mailbus.ports.AgentDirectory agents =
                new io.github.hopewang123456.mailbus.ports.AgentDirectory() {
                    @Override public void upsert(io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard card) {}
                    @Override public java.util.Optional<io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard> findById(String id) {
                        return java.util.Optional.empty();
                    }
                    @Override public java.util.List<io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard> findAll() {
                        return java.util.List.of();
                    }
                    @Override public io.github.hopewang123456.mailbus.ports.AgentDirectory.LaunchResult launch(String agentId, String message) {
                        return new io.github.hopewang123456.mailbus.ports.AgentDirectory.LaunchResult(true, 0, "", "");
                    }
                    @Override public io.github.hopewang123456.mailbus.ports.AgentDirectory.LaunchResult probe(io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard card) {
                        return new io.github.hopewang123456.mailbus.ports.AgentDirectory.LaunchResult(true, 0, "", "");
                    }
                };

        MailbusMetricsCalculator calc = new MailbusMetricsCalculator(manifest, messages, agents);

        assertTrue(calc.hasSource("bus.messages_total"));
        assertTrue(calc.hasSource("agents.total"));
        assertFalse(calc.hasSource("tasks.active")); // M1 无任务数据源 → 显式无源
        assertNull(calc.currentValue("tasks.active"));
        assertEquals(0d, calc.currentValue("bus.messages_total"));
        assertEquals(0d, calc.currentValue("agents.total"));
    }
}
