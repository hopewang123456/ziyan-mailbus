package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.AgentDirectory;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * mailbus 指标计算器（P2 B1 同源，D8 java 路径的取值核心）。
 *
 * <p>读双栈共享 manifest；按 source 分发到 java 端口实现（2026-10-28
 * 技术债批次三：M1 2 source → 7 source 全覆盖，11 指标对齐 python
 * {@code lib.adapters.metrics.collector} 口径）：
 * <ul>
 *   <li>messages → MessageRepository（bus.messages_total / bus.unread）</li>
 *   <li>agents → config.json agents ∪ builtin identities（agents.total /
 *       agents.online——python merge_into_agents 口径）</li>
 *   <li>tasks → TaskRepository（tasks.active / tasks.failed_today）</li>
 *   <li>tasks_b → TaskRepository + audit.jsonl（cycle_avg / interventions_week）</li>
 *   <li>tokens → ledger/tokens-&lt;today&gt;.jsonl（今日估算）</li>
 *   <li>alerts → alerts.json</li>
 *   <li>human_queue → HumanQueueService</li>
 * </ul>
 *
 * <p>bus.unread 终态口径说明：python 侧 7 终态 {done, closed, rejected,
 * failed, archived, sent, acknowledged}；java 消息库 state 值域为 java
 * MessageState 枚举（PENDING/PUSHED/PROCESSING/DONE/ACKNOWLEDGED/REJECTED/
 * ARCHIVED），其中终态 4 个——closed/failed/sent 是 python 侧独有状态名，
 * java 数据不出现，故两侧语义等价。
 *
 * <p>Micrometer 注册（boot 层 MailbusMetricsBinder）与 REST 查询
 * （api 层 MetricsController / StreamController）共用本类。
 */
public class MailbusMetricsCalculator {

    /** manifest 的 7 类 source 全部可算（M1 期 messages/agents → 全量）。 */
    private static final Set<String> SOURCES =
            Set.of("messages", "agents", "tasks", "tasks_b", "tokens", "alerts", "human_queue");

    /** 与 python _TERMINAL_MSG 对齐的判断集（见类注释口径说明）。 */
    private static final List<String> TERMINAL =
            List.of("DONE", "ACKNOWLEDGED", "REJECTED", "ARCHIVED");

    private static final Set<String> ACTIVE_TASK_STATUS = Set.of("running", "pending", "blocked");
    private static final Set<String> FAILED_TASK_STATUS = Set.of("failed", "timeout");

    private final MetricsManifestService manifest;
    private final MessageRepository messages;
    private final AgentDirectory agents;
    // 批次三扩展依赖（旧构造为 null → 相关指标 no_source 降级）
    private final TaskRepository tasks;
    private final HumanQueueService humanQueue;
    private final Path dataDir;
    private final BuiltinIdentitiesService builtinIdentities;

    public MailbusMetricsCalculator(MetricsManifestService manifest,
                                    MessageRepository messages,
                                    AgentDirectory agents) {
        this(manifest, messages, agents, null, null, null, null);
    }

    public MailbusMetricsCalculator(MetricsManifestService manifest,
                                    MessageRepository messages,
                                    AgentDirectory agents,
                                    TaskRepository tasks,
                                    HumanQueueService humanQueue,
                                    Path dataDir,
                                    BuiltinIdentitiesService builtinIdentities) {
        this.manifest = manifest;
        this.messages = messages;
        this.agents = agents;
        this.tasks = tasks;
        this.humanQueue = humanQueue;
        this.dataDir = dataDir;
        this.builtinIdentities = builtinIdentities;
    }

    /** 现算单值；依赖未注入或指标未实现 → null（调用方显式报错）。 */
    public Double currentValue(String metricId) {
        return switch (metricId) {
            case "bus.messages_total" -> (double) messages.countByAgentAndState().stream()
                    .mapToLong(MessageRepository.AgentStateCount::count).sum();
            case "bus.unread" -> (double) messages.countByAgentAndState().stream()
                    .filter(c -> !TERMINAL.contains(c.state()))
                    .mapToLong(MessageRepository.AgentStateCount::count).sum();
            case "agents.total" -> agentTotal();
            case "agents.online" -> agentsOnline();
            case "tasks.active" -> withTasks(() -> tasks.listAll().stream()
                    .filter(t -> ACTIVE_TASK_STATUS.contains(String.valueOf(t.get("status"))))
                    .count());
            case "tasks.failed_today" -> withTasks(() -> {
                String today = LocalDate.now(MetricsSources.localZone()).toString();
                return tasks.listAll().stream()
                        .filter(t -> FAILED_TASK_STATUS.contains(String.valueOf(t.get("status"))))
                        .filter(t -> String.valueOf(t.getOrDefault("updated_at",
                                t.getOrDefault("created_at", ""))).startsWith(today))
                        .count();
            });
            case "tasks.cycle_avg_minutes" -> cycleAvgMinutes();
            case "tasks.interventions_week" -> dataDir == null ? null
                    : MetricsSources.auditInterventionsWeek(dataDir);
            case "tokens.today_estimated" -> dataDir == null ? null
                    : MetricsSources.tokensTodayEstimate(dataDir);
            case "alerts.active" -> dataDir == null ? null
                    : MetricsSources.alertsActiveCount(dataDir);
            case "humanqueue.pending" -> humanQueue == null ? null
                    : (double) humanQueue.items().stream()
                            .filter(i -> "pending".equals(String.valueOf(i.get("status"))))
                            .count();
            default -> null;
        };
    }

    /** 该指标的 source 是否有数据源（manifest source 全集判断）。 */
    public boolean hasSource(String metricId) {
        for (Map<String, Object> m : manifest.metrics()) {
            if (String.valueOf(m.get("id")).equals(metricId)) {
                String source = String.valueOf(m.getOrDefault("source", ""));
                if (!SOURCES.contains(source)) {
                    return false;
                }
                // 依赖未注入的降级（旧构造路径）：相应 source 不可算。
                // agents 例外：总有 AgentDirectory 降级（见 agentTotal）
                return switch (source) {
                    case "tasks", "tasks_b" -> tasks != null;
                    case "tokens", "alerts" -> dataDir != null;
                    case "human_queue" -> humanQueue != null;
                    case "agents" -> true;
                    default -> true;
                };
            }
        }
        return false;
    }

    // ── agents（python merge_into_agents 口径：config agents ∪ builtin ids）──

    private Set<String> agentIds() {
        Set<String> ids = new HashSet<>();
        if (dataDir != null) {
            Map<String, Object> cfgAgents = readConfigAgents();
            if (cfgAgents != null) {
                ids.addAll(cfgAgents.keySet());
            }
        }
        if (builtinIdentities != null) {
            Object identities = builtinIdentities.list().get("identities");
            if (identities instanceof List<?> list) {
                for (Object o : list) {
                    if (o instanceof Map<?, ?> m) {
                        String id = String.valueOf(m.get("id"));
                        if (!id.isBlank()) {
                            ids.add(id);
                        }
                    }
                }
            }
        }
        return ids;
    }

    private Double agentTotal() {
        Set<String> ids = agentIds();
        if (ids.isEmpty()) {
            // 降级：config/builtin 不可得时沿用 AgentDirectory（CLI 卡片口径）
            return (double) agents.findAll().size();
        }
        return (double) ids.size();
    }

    private Double agentsOnline() {
        if (dataDir == null) {
            return null;
        }
        Set<String> ids = agentIds();
        if (ids.isEmpty()) {
            return null;
        }
        return (double) MetricsSources.heartbeatOnlineCount(dataDir, ids);
    }

    // ── tasks_b ──────────────────────────────────────────────────────────

    private Double cycleAvgMinutes() {
        if (tasks == null) {
            return null;
        }
        Instant weekAgo = Instant.now().minus(Duration.ofDays(7));
        List<Double> durations = new ArrayList<>();
        for (Map<String, Object> t : tasks.listAll()) {
            if (!"success".equals(String.valueOf(t.get("status")))) {
                continue;
            }
            Instant updated = MetricsSources.parseInstant(String.valueOf(t.get("updated_at")));
            Instant created = MetricsSources.parseInstant(String.valueOf(t.get("created_at")));
            if (updated == null || created == null || updated.isBefore(weekAgo)) {
                continue;
            }
            durations.add((updated.toEpochMilli() - created.toEpochMilli()) / 60000.0);
        }
        if (durations.isEmpty()) {
            return 0.0;
        }
        double avg = durations.stream().mapToDouble(Double::doubleValue).average().orElse(0);
        return Math.round(avg * 10) / 10.0;
    }

    private Double withTasks(java.util.function.LongSupplier fn) {
        if (tasks == null) {
            return null;
        }
        return (double) fn.getAsLong();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readConfigAgents() {
        if (dataDir == null) {
            return null;
        }
        try {
            Map<String, Object> cfg = MetricsSources.Json.MAPPER.readValue(
                    java.nio.file.Files.readString(dataDir.resolve("config.json")), Map.class);
            return cfg.get("agents") instanceof Map<?, ?> m ? (Map<String, Object>) m : null;
        } catch (Exception e) {
            return null;
        }
    }
}
