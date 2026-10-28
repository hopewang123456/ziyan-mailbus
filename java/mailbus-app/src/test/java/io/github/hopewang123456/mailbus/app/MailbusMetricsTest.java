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
    // ── 批次三（2026-10-28）：7 source 全覆盖路径 ──────────────────────────

    @Test
    void fullSourcesComputeAllMetricFamilies(@TempDir Path dataDir) throws IOException {
        Path root = seedRoot(Files.createTempDirectory("seed2"));
        MetricsManifestService manifest = new MetricsManifestService(dataDir, root);
        var messages = new io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository();

        // store 侧最小 fixture：任务池 + human-queue + alerts + audit + ledger
        Files.createDirectories(dataDir.resolve("tasks"));
        Files.writeString(dataDir.resolve("tasks/t-1.json"), """
                {"task_id": "t-1", "status": "running", "created_at": "2026-10-28T01:00:00Z",
                 "updated_at": "2026-10-28T02:00:00Z"}
                """);
        Files.writeString(dataDir.resolve("human-queue.json"), """
                {"items": [{"id": "h1", "status": "pending"}, {"id": "h2", "status": "done"}]}
                """);
        Files.writeString(dataDir.resolve("alerts.json"), """
                {"alerts": [{"id": "a1"}, {"id": "a2"}]}
                """);
        Files.createDirectories(dataDir.resolve("system"));
        Files.writeString(dataDir.resolve("system/audit.jsonl"),
                "{\"event\": \"human_gate.resolve\", \"ts\": \"2026-10-28T01:00:00Z\"}\n"
                + "{\"event\": \"other\", \"ts\": \"2026-10-28T01:00:00Z\"}\n");
        String today = java.time.LocalDate.now(
                java.time.ZoneId.of("Asia/Shanghai")).toString();
        Files.createDirectories(dataDir.resolve("ledger"));
        Files.writeString(dataDir.resolve("ledger/tokens-" + today + ".jsonl"),
                "{\"est_tokens\": 120, \"agent\": \"a\"}\n" + "{\"est_tokens\": 30, \"agent\": \"b\"}\n");

        var tasks = new io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository(dataDir);
        var clock = java.time.Clock.systemUTC();
        MailbusMetricsCalculator calc = new MailbusMetricsCalculator(
                manifest, messages, agentStub(), tasks,
                new HumanQueueService(dataDir, clock), dataDir,
                new BuiltinIdentitiesService(dataDir, root));

        // 新 source 全部 hasSource 且可算
        assertTrue(calc.hasSource("tasks.active"));
        assertEquals(1d, calc.currentValue("tasks.active"));
        assertEquals(2d, calc.currentValue("alerts.active"));
        assertEquals(1d, calc.currentValue("humanqueue.pending"));
        assertEquals(1d, calc.currentValue("tasks.interventions_week"));
        assertEquals(150d, calc.currentValue("tokens.today_estimated"));
        // config.json 无 agents 段 + seed 无 builtin → 退回 AgentDirectory（0）
        assertEquals(0d, calc.currentValue("agents.total"));
        // cycle_avg：无 success 任务 → 0（python 同语义）
        assertEquals(0d, calc.currentValue("tasks.cycle_avg_minutes"));
    }

    private io.github.hopewang123456.mailbus.ports.AgentDirectory agentStub() {
        return new io.github.hopewang123456.mailbus.ports.AgentDirectory() {
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
    }
}
