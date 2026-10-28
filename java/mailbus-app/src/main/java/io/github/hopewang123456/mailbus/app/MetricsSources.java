package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/**
 * 共享 store 文件的只读指标解析器（2026-10-28 技术债批次三）— python
 * {@code lib.adapters.metrics.collector} 各 source 的 java 对等口径。
 *
 * <p>只读 {@code shared/store} 布局（双栈同池）：heartbeat.json /
 * heartbeat.*.json / ledger/tokens-*.jsonl / system/audit.jsonl / alerts.json。
 * 零 Spring 依赖（app 层纪律）。
 *
 * <p>时间口径注意：python 侧日期分片用本地时区（环境 TZ=Asia/Shanghai），
 * java 侧 domain 纪律是 UTC——token 台账「今日」与任务「今日」按
 * <b>Asia/Shanghai</b> 日期对齐 python（否则两侧差 8 小时分片）。
 */
public final class MetricsSources {

    private MetricsSources() {
    }

    /** python 侧日期分片时区（对齐口径，非 domain 纪律的例外说明）。 */
    private static final ZoneId LOCAL_TZ = ZoneId.of("Asia/Shanghai");

    /** 日期分片时区（与 python 本地时区对齐；Calculator 复用）。 */
    static ZoneId localZone() {
        return LOCAL_TZ;
    }

    // ── agents.online（python is_online：无记录=true，status=="online"）──

    public static int heartbeatOnlineCount(Path dataDir, java.util.Set<String> agentIds) {
        Map<String, Map<String, Object>> status = new HashMap<>();
        // 1) bus 共享心跳
        Map<String, Object> bus = readMap(dataDir.resolve("heartbeat.json"));
        if (bus != null && bus.get("agents") instanceof Map<?, ?> m) {
            for (var e : m.entrySet()) {
                if (e.getValue() instanceof Map<?, ?> am) {
                    status.put(String.valueOf(e.getKey()), toStringMap(am));
                }
            }
        }
        // 2) per-agent daemon 心跳（heartbeat.{agent}.json 覆盖 bus 状态）
        try (Stream<Path> files = Files.list(dataDir)) {
            files.map(p -> p.getFileName().toString())
                    .filter(n -> n.startsWith("heartbeat.") && n.endsWith(".json") && n.length() > "heartbeat..json".length())
                    .forEach(n -> {
                        Map<String, Object> hb = readMap(dataDir.resolve(n));
                        if (hb != null && !String.valueOf(hb.get("agent")).isBlank()) {
                            status.put(String.valueOf(hb.get("agent")), hb);
                        }
                    });
        } catch (IOException ignored) {
            // 目录不可读：退化为 bus 心跳
        }
        int online = 0;
        for (String id : agentIds) {
            Map<String, Object> agent = status.get(id);
            if (agent == null || "online".equals(String.valueOf(agent.get("status")))) {
                online++; // python 语义：无心跳记录视为在线（缺省 true）
            }
        }
        return online;
    }

    // ── tokens.today_estimated（python today_summary：est_tokens 汇总）──

    public static double tokensTodayEstimate(Path dataDir) {
        String day = LocalDate.now(LOCAL_TZ).toString();
        Path ledger = dataDir.resolve("ledger").resolve("tokens-" + day + ".jsonl");
        if (!Files.isRegularFile(ledger)) {
            return 0.0;
        }
        long total = 0;
        try {
            for (String line : Files.readAllLines(ledger)) {
                Map<String, Object> e = readJsonLine(line);
                if (e == null) {
                    continue;
                }
                total += parseLong(e.get("est_tokens"));
            }
        } catch (IOException ignored) {
            return 0.0;
        }
        return (double) total;
    }

    // ── tasks.interventions_week（audit.jsonl 近 7 天 human_gate.resolve）──

    public static double auditInterventionsWeek(Path dataDir) {
        Path audit = dataDir.resolve("system").resolve("audit.jsonl");
        if (!Files.isRegularFile(audit)) {
            return 0.0;
        }
        Instant weekAgo = Instant.now().minus(Duration.ofDays(7));
        long count = 0;
        try {
            for (String line : Files.readAllLines(audit)) {
                Map<String, Object> ev = readJsonLine(line);
                if (ev == null || !"human_gate.resolve".equals(String.valueOf(ev.get("event")))) {
                    continue;
                }
                Instant ts = parseInstant(String.valueOf(ev.getOrDefault("ts", "")));
                if (ts != null && !ts.isBefore(weekAgo)) {
                    count++;
                }
            }
        } catch (IOException ignored) {
            return 0.0;
        }
        return (double) count;
    }

    // ── alerts.active（python get_recent_alerts(limit=50)：尾部 50 条计数）──

    public static double alertsActiveCount(Path dataDir) {
        Map<String, Object> doc = readMap(dataDir.resolve("alerts.json"));
        if (doc == null || !(doc.get("alerts") instanceof List<?> alerts)) {
            return 0.0;
        }
        int from = Math.max(0, alerts.size() - 50);
        return (double) (alerts.size() - from);
    }

    // ── helpers ──────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private static Map<String, Object> readMap(Path path) {
        if (!Files.isRegularFile(path)) {
            return null;
        }
        try {
            return Json.MAPPER.readValue(Files.readString(path), Map.class);
        } catch (IOException | ClassCastException e) {
            return null;
        }
    }

    private static Map<String, Object> readJsonLine(String line) {
        line = line == null ? "" : line.trim();
        if (line.isEmpty()) {
            return null;
        }
        try {
            return Json.MAPPER.readValue(line, Map.class);
        } catch (IOException e) {
            return null;
        }
    }

    private static long parseLong(Object v) {
        if (v instanceof Number n) {
            return n.longValue();
        }
        try {
            return Long.parseLong(String.valueOf(v));
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /** python parse_iso_dt 的容错子集：ISO-8601 / ISO 本地日期时间。 */
    static Instant parseInstant(String ts) {
        if (ts == null || ts.isBlank()) {
            return null;
        }
        try {
            return Instant.parse(ts);
        } catch (Exception ignored) {
            // fall through
        }
        try {
            return java.time.LocalDateTime.parse(ts.trim().replaceFirst("\\+0800$", ""))
                    .atZone(LOCAL_TZ).toInstant();
        } catch (Exception ignored) {
            return null;
        }
    }

    private static Map<String, Object> toStringMap(Map<?, ?> m) {
        Map<String, Object> out = new HashMap<>();
        for (var e : m.entrySet()) {
            out.put(String.valueOf(e.getKey()), e.getValue());
        }
        return out;
    }

    /** Jackson 共享实例（com.fasterxml 在 app 层已由 MetricsManifestService 先例使用）。 */
    static final class Json {
        static final com.fasterxml.jackson.databind.ObjectMapper MAPPER =
                new com.fasterxml.jackson.databind.ObjectMapper();
    }
}
