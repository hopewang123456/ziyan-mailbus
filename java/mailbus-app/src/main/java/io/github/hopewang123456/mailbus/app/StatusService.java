package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

/**
 * Bus overview aggregates for the cockpit first screen — the python
 * /api/status and /api/stats counterparts (minimal first-screen fields).
 */
public class StatusService {

    private static final java.util.Set<String> TERMINAL = java.util.Set.of(
            "DONE", "ACKNOWLEDGED", "REJECTED", "ARCHIVED");

    private final MessageRepository repository;

    public StatusService(MessageRepository repository) {
        this.repository = repository;
    }

    /** GET /api/status — {project, total, unread, agents:{name:{active_messages,has_unread,type}}} */
    public Map<String, Object> status() {
        Map<String, Object> agentStatuses = new TreeMap<>();
        long total = 0, unread = 0;
        for (var c : repository.countByAgentAndState()) {
            total += c.count();
            if (!TERMINAL.contains(c.state())) {
                unread += c.count();
            }
        }
        // per-agent rollup
        Map<String, long[]> per = new TreeMap<>(); // [active, nonTerminal]
        Map<String, Boolean> any = new TreeMap<>();
        for (var c : repository.countByAgentAndState()) {
            long[] a = per.computeIfAbsent(c.agent(), k -> new long[2]);
            a[0] += c.count();
            if (!TERMINAL.contains(c.state())) {
                a[1] += c.count();
            }
            any.put(c.agent(), true);
        }
        per.forEach((name, a) -> agentStatuses.put(name, Map.of(
                "active_messages", a[0],
                "has_unread", a[1] > 0,
                "type", "agent"))); // type refinement arrives with the M3 agents table
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("project", "mailbus-j");
        out.put("implementation", "java");
        out.put("total", total);
        out.put("unread", unread);
        out.put("agents", agentStatuses);
        return out;
    }

    /** GET /api/stats — {total_messages, status_distribution, agent_stats} */
    public Map<String, Object> stats() {
        Map<String, Long> statusDist = new TreeMap<>();
        Map<String, Map<String, Long>> agentStats = new TreeMap<>();
        long total = 0;
        for (var c : repository.countByAgentAndState()) {
            total += c.count();
            statusDist.merge(c.state().toLowerCase(), c.count(), Long::sum);
            agentStats.computeIfAbsent(c.agent(), k -> new TreeMap<>())
                    .merge(c.state().toLowerCase(), c.count(), Long::sum);
        }
        return Map.of(
                "total_messages", total,
                "status_distribution", statusDist,
                "agent_stats", agentStats);
    }
}
