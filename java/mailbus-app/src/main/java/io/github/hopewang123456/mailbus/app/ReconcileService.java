package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.MessageRepository;
import io.github.hopewang123456.mailbus.ports.StoreMigrator;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * D16 批4：消息存储 SoT 统一后的对账口径 —— python {@code inbox.json} 是唯一
 * 事实源，java {@code msg_index} 降级为投影缓存。
 *
 * <p>因此：
 * <ul>
 *   <li>{@code javaOnly} 不再意味「伪造」，而是<b>投影滞后</b>——用
 *       {@code mailbus msg-index rebuild} 全量重刷即可归零；</li>
 *   <li>{@code python > java} 是正常状态（投影未重建时），不是漂移；</li>
 *   <li>状态词表两侧已同源（python 终态口径），未知状态仍以 notes 暴露，不做猜测。</li>
 * </ul>
 */
public class ReconcileService {

    public record Report(long pythonTotal, long javaTotal, long javaOnlyCount,
                         List<String> javaOnlySample,
                         Map<String, Long> pythonStates, Map<String, Long> javaStates,
                         Map<String, Long> perAgentDelta, List<String> notes) {}

    private final MessageRepository repository;

    public ReconcileService(MessageRepository repository) {
        this.repository = repository;
    }

    public Report reconcile(Path pythonStoreRoot, StoreMigrator migrator) {
        StoreMigrator.Result py = migrator.readAll();

        Map<String, Long> pyStates = new TreeMap<>();
        Map<String, Long> javaStates = new TreeMap<>();
        Map<String, Long> pyPerAgent = new TreeMap<>();
        for (StoreMigrator.RawMessage m : py.messages()) {
            pyStates.merge(m.record().state().name(), 1L, Long::sum);
            pyPerAgent.merge(m.record().toAgent(), 1L, Long::sum);
        }
        for (var c : repository.countByAgentAndState()) {
            javaStates.merge(c.state(), c.count(), Long::sum);
        }

        // id-level diff: java messages absent from the python snapshot
        java.util.Set<String> pyIds = new java.util.HashSet<>();
        py.messages().forEach(m -> pyIds.add(m.record().id()));
        List<String> javaOnly = new ArrayList<>();
        for (String id : repository.allIds()) {
            if (!pyIds.contains(id)) {
                javaOnly.add(id);
            }
        }

        Map<String, Long> delta = new TreeMap<>();
        Map<String, Long> javaPerAgent = new TreeMap<>();
        for (var c : repository.countByAgentAndState()) {
            javaPerAgent.merge(c.agent(), c.count(), Long::sum);
        }
        for (var e : pyPerAgent.entrySet()) {
            long d = e.getValue() - javaPerAgent.getOrDefault(e.getKey(), 0L);
            if (d != 0) {
                delta.put(e.getKey(), d);
            }
        }
        for (var e : javaPerAgent.entrySet()) {
            if (!pyPerAgent.containsKey(e.getKey()) && e.getValue() > 0) {
                delta.put(e.getKey(), -e.getValue()); // java has, python lacks
            }
        }

        List<String> notes = new ArrayList<>(py.warnings());
        notes.add("files lead: msg_index is a projection of python inbox.json "
                + "(rebuild with `mailbus msg-index rebuild`)");
        if (javaOnly.size() > 0) {
            notes.add("java-only ids = projection lag, NOT fabrication: "
                    + "run `mailbus msg-index rebuild` (or `mailbus migrate-shards` "
                    + "for pre-D16 java shard files) and re-run");
        }
        return new Report(py.messages().size(),
                javaStates.values().stream().mapToLong(Long::longValue).sum(),
                javaOnly.size(), javaOnly.stream().limit(5).toList(),
                pyStates, javaStates, delta, notes);
    }
}
