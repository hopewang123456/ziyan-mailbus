package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.AgentDirectory;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * mailbus 指标计算器（P2 B1 同源，D8 java 路径的取值核心）。
 *
 * <p>读双栈共享 manifest；按 source 分发到 java 端口实现：
 * messages → MessageRepository，agents → AgentDirectory。
 * M1 无数据源的指标（tasks/tokens/alerts/human_queue）由调用方显式报
 * {@code no_source_in_m1}（不静默 0）。Micrometer 注册（boot 层
 * MailbusMetricsBinder）与 REST 查询（api 层 MetricsController）共用本类。
 */
public class MailbusMetricsCalculator {

    private static final Set<String> M1_SOURCES = Set.of("messages", "agents");
    private static final List<String> TERMINAL =
            List.of("DONE", "ACKNOWLEDGED", "REJECTED", "ARCHIVED");

    private final MetricsManifestService manifest;
    private final MessageRepository messages;
    private final AgentDirectory agents;

    public MailbusMetricsCalculator(MetricsManifestService manifest,
                                    MessageRepository messages,
                                    AgentDirectory agents) {
        this.manifest = manifest;
        this.messages = messages;
        this.agents = agents;
    }

    /** 现算单值；无 M1 数据源 → null（调用方显式报错）。 */
    public Double currentValue(String metricId) {
        return switch (metricId) {
            case "bus.messages_total" -> (double) messages.countByAgentAndState().stream()
                    .mapToLong(c -> c.count()).sum();
            case "bus.unread" -> (double) messages.countByAgentAndState().stream()
                    .filter(c -> !TERMINAL.contains(c.state()))
                    .mapToLong(c -> c.count()).sum();
            case "agents.total" -> (double) agents.findAll().size();
            default -> null;
        };
    }

    /** 该指标在 java M1 侧是否有数据源。 */
    public boolean hasSource(String metricId) {
        for (Map<String, Object> m : manifest.metrics()) {
            if (String.valueOf(m.get("id")).equals(metricId)) {
                return M1_SOURCES.contains(String.valueOf(m.getOrDefault("source", "")));
            }
        }
        return false;
    }
}
