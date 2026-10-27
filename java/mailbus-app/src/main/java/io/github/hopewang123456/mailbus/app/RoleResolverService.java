package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.task.StepFsmState;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 职位派发解析 — python {@code dispatch/role_resolver.py resolve_agent_for_role_type}
 * 对等：pin（指定）> 空闲优先（负载感知）> round-robin 兜底（D3 职位与角色分离）。
 *
 * <p>数据源全部为 python 兼容文件：config.json（agents/dispatch 段）、
 * roles/json/role-types.json（候选池 SoT）、tasks/*.json（活跃负载）、
 * dispatch/role-round-robin.json（游标）。
 */
public class RoleResolverService {

    private static final int DEFAULT_CONCURRENCY = 1;
    private static final int TIER_ORDER_S = 0;

    private final Path dataDir;
    private final TaskRepository tasks;

    public RoleResolverService(Path dataDir, TaskRepository tasks) {
        this.dataDir = dataDir;
        this.tasks = tasks;
    }

    /** 解析结果：agent + dispatch_meta（写进 chain[0].dispatch_meta 的形状与 python 一致）。 */
    public record Resolved(String agent, Map<String, Object> meta) {
    }

    public Resolved resolve(int roleType, String pinAgent) {
        return resolve(roleType, pinAgent, Set.of());
    }

    @SuppressWarnings("unchecked")
    public Resolved resolve(int roleType, String pinAgent, Set<String> exclude) {
        Map<String, Object> config = orEmpty(JsonFiles.readMap(dataDir.resolve("config.json")));
        Map<String, Object> agentsCfg = orEmpty((Map<String, Object>) config.get("agents"));

        if (pinAgent != null && !pinAgent.isEmpty() && !exclude.contains(pinAgent)
                && agentDispatchable(pinAgent, agentsCfg)) {
            return new Resolved(pinAgent, meta("pin", roleType, pinAgent));
        }

        List<String> candidates = roleCandidates(roleType);
        List<String> dispatchable = candidates.stream()
                .filter(c -> !exclude.contains(c) && agentDispatchable(c, agentsCfg))
                .toList();
        List<String> pool = dispatchable.isEmpty()
                ? candidates.stream().filter(c -> !exclude.contains(c)).toList()
                : dispatchable;

        Map<String, Object> dispatchCfg = orEmpty((Map<String, Object>) config.get("dispatch"));
        boolean loadAware = !Boolean.FALSE.equals(dispatchCfg.get("load_aware"));
        int defaultConcurrency = intOr(dispatchCfg.get("default_concurrency"), DEFAULT_CONCURRENCY);

        if (loadAware && !dispatchable.isEmpty()) {
            Map<String, Integer> active = activeLoad();
            Set<String> busy = busyAgents(active, agentsCfg, defaultConcurrency);
            List<String> idle = dispatchable.stream().filter(c -> !busy.contains(c)).toList();
            if (!idle.isEmpty()) {
                String agent = idle.get(0); // 候选顺序即适配度顺序
                Map<String, Object> meta = meta("idle_first", roleType, agent);
                meta.put("candidates", candidates);
                meta.put("skipped_busy", dispatchable.stream().filter(busy::contains).toList());
                meta.put("load", active.getOrDefault(agent, 0));
                return new Resolved(agent, meta);
            }
        }
        return pickRoundRobin(roleType, pool);
    }

    /** 每 agent 活跃占用（扫任务池 chain 非终态步骤；python _active_load 对等）。 */
    public Map<String, Integer> activeLoad() {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (Map<String, Object> task : tasks.listAll()) {
            Object chain = task.get("chain");
            if (!(chain instanceof List<?> steps)) {
                continue;
            }
            Set<String> touched = new HashSet<>();
            for (Object s : steps) {
                if (!(s instanceof Map<?, ?> step)) {
                    continue;
                }
                String to = firstNonEmpty(step.get("to_agent"), step.get("to_person"));
                String state = firstNonEmpty(step.get("fsm_state"), step.get("status"));
                if (to != null && !StepFsmState.TERMINAL.contains(state)) {
                    touched.add(to);
                }
            }
            if (touched.isEmpty()) {
                String assignee = str(task.get("assignee"));
                if (!assignee.isEmpty()) {
                    touched.add(assignee);
                }
            }
            for (String agent : touched) {
                counts.merge(agent, 1, Integer::sum);
            }
        }
        return counts;
    }

    /** busy = 活跃数 >= 并发上限（python _busy_agents 对等）。 */
    public Set<String> busyAgents(Map<String, Integer> active, Map<String, Object> agentsCfg,
                                   int defaultConcurrency) {
        Set<String> busy = new HashSet<>();
        for (Map.Entry<String, Object> e : agentsCfg.entrySet()) {
            int limit = defaultConcurrency;
            if (e.getValue() instanceof Map<?, ?> cfg) {
                limit = intOr(cfg.get("concurrency"), defaultConcurrency);
            }
            if (limit <= 0) {
                continue;
            }
            if (active.getOrDefault(e.getKey(), 0) >= limit) {
                busy.add(e.getKey());
            }
        }
        return busy;
    }

    public boolean loadAwareEnabled() {
        Map<String, Object> config = orEmpty(JsonFiles.readMap(dataDir.resolve("config.json")));
        Map<String, Object> dispatchCfg = orEmpty(asMap(config.get("dispatch")));
        return !Boolean.FALSE.equals(dispatchCfg.get("load_aware"));
    }

    public int defaultConcurrency() {
        Map<String, Object> config = orEmpty(JsonFiles.readMap(dataDir.resolve("config.json")));
        Map<String, Object> dispatchCfg = orEmpty(asMap(config.get("dispatch")));
        return intOr(dispatchCfg.get("default_concurrency"), DEFAULT_CONCURRENCY);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> agentsConfig() {
        Map<String, Object> config = orEmpty(JsonFiles.readMap(dataDir.resolve("config.json")));
        return orEmpty((Map<String, Object>) config.get("agents"));
    }

    /** python _agent_dispatchable：config 内 available!=false；config 外看 inbox 目录。 */
    public boolean agentDispatchable(String agent, Map<String, Object> agentsCfg) {
        if (agent == null || agent.isEmpty()) {
            return false;
        }
        Object cfg = agentsCfg.get(agent);
        if (cfg instanceof Map<?, ?> m) {
            return !Boolean.FALSE.equals(m.get("available"));
        }
        if (agentsCfg.containsKey(agent)) {
            return true;
        }
        return java.nio.file.Files.isDirectory(dataDir.resolve("inbox").resolve(agent));
    }

    /** role-types.json 候选池（与 python 同一 SoT 文件）。 */
    @SuppressWarnings("unchecked")
    public List<String> roleCandidates(int roleType) {
        var root = JsonFiles.readTree(dataDir.resolve("roles/json/role-types.json"));
        if (root == null) {
            return List.of();
        }
        var entry = root.path("roles").path(String.valueOf(roleType));
        if (!entry.isObject()) {
            return List.of();
        }
        List<String> out = new ArrayList<>();
        entry.path("candidates").forEach(n -> out.add(n.asText()));
        return out;
    }

    private Resolved pickRoundRobin(int roleType, List<String> candidates) {
        Path rrPath = dataDir.resolve("dispatch/role-round-robin.json");
        Map<String, Object> doc = orEmpty(JsonFiles.readMap(rrPath));
        if (doc.isEmpty()) {
            doc.put("version", "1.0.0");
            doc.put("cursors", new LinkedHashMap<String, Object>());
        }
        Map<String, Object> cursors = asMap(doc.get("cursors"));
        if (candidates.isEmpty()) {
            return new Resolved("", meta("round_robin_error", roleType, ""));
        }
        String key = String.valueOf(roleType);
        int idx = intOr(cursors.get(key), 0) % candidates.size();
        String agent = candidates.get(idx);
        cursors.put(key, idx + 1);
        doc.put("cursors", cursors);
        JsonFiles.write(rrPath, doc);
        Map<String, Object> meta = meta("round_robin", roleType, agent);
        meta.put("candidates", candidates);
        meta.put("index", idx);
        return new Resolved(agent, meta);
    }

    private static Map<String, Object> meta(String source, int roleType, String agent) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("source", source);
        m.put("role_type", roleType);
        if (agent != null && !agent.isEmpty()) {
            m.put("agent", agent);
        }
        return m;
    }

    private static String firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return String.valueOf(v);
            }
        }
        return null;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static int intOr(Object o, int fallback) {
        if (o instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(o));
        } catch (RuntimeException e) {
            return fallback;
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
    }

    private static Map<String, Object> orEmpty(Map<String, Object> m) {
        return m == null ? new LinkedHashMap<>() : m;
    }
}
