package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 职位目录（P1 发令窗口起草面板数据源，D3 职位≠角色）— python
 * {@code role_resolver.position_catalog} 的 java 对等实现。
 *
 * <p>SoT：{@code {dataDir}/roles/json/role-types.json}（与 python 同一份文件，
 * 双栈同一真源；inputs 为起草表单 schema，缺省空列表兼容存量）。
 *
 * <p>M2a 起 busy/active_tasks/available 由 {@link RoleResolverService} 读
 * 共享任务池提供真值（此前恒 false/0 的占位已对齐 python）。
 */
public class PositionCatalogService {

    private final Path roleTypesPath;
    private final RoleResolverService resolver;

    public PositionCatalogService(Path dataDir) {
        this(dataDir, null);
    }

    public PositionCatalogService(Path dataDir, RoleResolverService resolver) {
        this.roleTypesPath = dataDir.resolve("roles/json/role-types.json");
        this.resolver = resolver;
    }

    /** GET /api/positions — {status, positions:[...], total}. */
    public Map<String, Object> catalog() {
        Map<String, Object> agentsCfg = resolver != null ? resolver.agentsConfig() : Map.of();
        Map<String, Integer> active = resolver != null ? resolver.activeLoad() : Map.of();
        java.util.Set<String> busy = resolver != null && resolver.loadAwareEnabled()
                ? resolver.busyAgents(active, agentsCfg, resolver.defaultConcurrency())
                : java.util.Set.of();
        List<Map<String, Object>> positions = new ArrayList<>();
        Map<String, Object> roles = readRoles();
        roles.entrySet().stream()
                .sorted(Comparator.comparingInt(e -> parseIntOr(e.getKey(), 0)))
                .forEach(e -> positions.add(toPosition(e.getKey(), asMap(e.getValue()),
                        agentsCfg, active, busy)));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("positions", positions);
        out.put("total", positions.size());
        return out;
    }

    private Map<String, Object> toPosition(String roleType, Map<String, Object> entry,
                                           Map<String, Object> agentsCfg,
                                           Map<String, Integer> active, java.util.Set<String> busy) {
        Map<String, Object> display = asMap(entry.get("display"));
        List<Map<String, Object>> candidates = new ArrayList<>();
        for (Object c : asList(entry.get("candidates"))) {
            String agentId = String.valueOf(c);
            Map<String, Object> meta = asMap(agentsCfg.get(agentId));
            Map<String, Object> cand = new LinkedHashMap<>();
            cand.put("agent_id", agentId);
            cand.put("name", String.valueOf(meta.getOrDefault("name", agentId)));
            cand.put("framework", String.valueOf(meta.getOrDefault("type",
                    meta.getOrDefault("framework", ""))));
            cand.put("available", resolver == null
                    || resolver.agentDispatchable(agentId, agentsCfg));
            cand.put("busy", busy.contains(agentId));
            cand.put("active_tasks", active.getOrDefault(agentId, 0));
            candidates.add(cand);
        }
        Map<String, Object> pos = new LinkedHashMap<>();
        pos.put("role_type", parseIntOr(roleType, 0));
        pos.put("key", String.valueOf(entry.getOrDefault("key", "role_" + roleType)));
        pos.put("name_zh", String.valueOf(display.getOrDefault("zh", "")));
        pos.put("name_en", String.valueOf(display.getOrDefault("en", "")));
        pos.put("default_sla_minutes", entry.get("default_sla_minutes"));
        pos.put("inputs", asList(entry.get("inputs")));
        pos.put("candidates", candidates);
        return pos;
    }

    private Map<String, Object> readRoles() {
        if (!Files.isRegularFile(roleTypesPath)) {
            return Map.of();
        }
        try {
            String json = Files.readString(roleTypesPath);
            // 走 jackson（模块已有依赖），避免手搓 JSON 解析
            com.fasterxml.jackson.databind.JsonNode root =
                    new com.fasterxml.jackson.databind.ObjectMapper().readTree(json);
            Map<String, Object> roles = new LinkedHashMap<>();
            root.path("roles").fields().forEachRemaining(f -> roles.put(f.getKey(), treeToMap(f.getValue())));
            return roles;
        } catch (IOException e) {
            return Map.of();
        }
    }

    private static Object treeToMap(com.fasterxml.jackson.databind.JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isObject()) {
            Map<String, Object> m = new LinkedHashMap<>();
            node.fields().forEachRemaining(f -> m.put(f.getKey(), treeToMap(f.getValue())));
            return m;
        }
        if (node.isArray()) {
            List<Object> l = new ArrayList<>();
            node.forEach(n -> l.add(treeToMap(n)));
            return l;
        }
        if (node.isIntegralNumber()) {
            return node.asLong();
        }
        if (node.isNumber()) {
            return node.asDouble();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        return node.asText();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : Map.of();
    }

    @SuppressWarnings("unchecked")
    private static List<Object> asList(Object o) {
        return o instanceof List<?> l ? (List<Object>) l : List.of();
    }

    private static int parseIntOr(String s, int fallback) {
        try {
            return Integer.parseInt(s.trim());
        } catch (RuntimeException e) {
            return fallback;
        }
    }
}
