package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.MessageRepository;
import io.github.hopewang123456.mailbus.ports.StoreMigrator;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Dual-run reconciliation (M4): python store (live) vs java store (migrated
 * snapshot). Reports totals, per-state distribution, per-agent deltas and
 * java-only ids — the go/no-go evidence for "switchable".
 *
 * Semantics: the java side is a point-in-time migration, so python > java on
 * a live system is expected growth, not drift. What matters: java NEVER has
 * messages python lacks (fabrication), and unmapped state words surface as
 * notes, never guesses.
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
        notes.add("point-in-time: python>java on a live system is growth, not drift");
        if (javaOnly.size() > 0) {
            notes.add("java-only ids include BOTH java-local test traffic AND messages the "
                    + "python side archived/cleaned after the migration snapshot — "
                    + "verify against archive/ trees before treating as fabrication");
        }
        return new Report(py.messages().size(),
                javaStates.values().stream().mapToLong(Long::longValue).sum(),
                javaOnly.size(), javaOnly.stream().limit(5).toList(),
                pyStates, javaStates, delta, notes);
    }
}
