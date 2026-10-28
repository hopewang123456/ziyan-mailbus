package io.github.hopewang123456.mailbus.app;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 驾驶舱配置面（P2 B4/B5，2026-10-27 PY4-A）— java 对等实现。
 *
 * <p>两处配置与 python 同源同优先级：
 * <ul>
 *   <li>大盘布局（layout）：{@code {dataDir}/config/dashboard-layout.json}
 *       —— 缺省 {@code {"hidden": []}}；</li>
 *   <li>告警规则（rules）：seed {@code shared/config/mailbus/alert-rules.json}
 *       + 按 id 逐条覆盖 {@code {dataDir}/config/alert-rules.json}
 *       （与 python {@code lib.adapters.metrics.rules.load_rules} 同语义）。</li>
 * </ul>
 *
 * <p>零 Spring 依赖（app 层纪律）；属性值由调用方传入。
 */
public class DashboardConfigService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Path dataDir;
    private final Path mailbusRoot;

    public DashboardConfigService(Path dataDir, Path mailbusRoot) {
        this.dataDir = dataDir;
        this.mailbusRoot = mailbusRoot;
    }

    // ── 大盘布局（B4）────────────────────────────────────────────────────

    /** 读取大盘布局；文件缺失时返回 {@code {"hidden": []}}。 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> layout() {
        Path p = dataDir.resolve("config/dashboard-layout.json");
        Map<String, Object> doc = readMap(p);
        if (doc == null || !(doc.get("hidden") instanceof List)) {
            return Map.of("hidden", List.of());
        }
        return doc;
    }

    /** 整体覆盖写大盘布局（PATCH 语义）。 */
    public Map<String, Object> saveLayout(List<String> hidden) {
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("hidden", hidden == null ? List.of() : List.copyOf(hidden));
        try {
            Path p = dataDir.resolve("config/dashboard-layout.json");
            Files.createDirectories(p.getParent());
            Files.writeString(p, MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(doc));
        } catch (IOException e) {
            throw new java.io.UncheckedIOException("layout write failed", e);
        }
        return doc;
    }

    // ── 告警规则（B5）────────────────────────────────────────────────────

    /**
     * 规则清单：seed 全量 + store 覆盖中同 id 的条目做字段级更新
     * （与 python {@code load_rules} 一致：覆盖是 update，不是整条替换）。
     */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> rules() {
        Path seed = mailbusRoot.resolve("config/mailbus/alert-rules.json");
        Map<String, Object> seedDoc = readMap(seed);
        Map<String, Map<String, Object>> byId = new LinkedHashMap<>();
        if (seedDoc != null && seedDoc.get("rules") instanceof List<?> raw) {
            for (Object o : raw) {
                if (o instanceof Map<?, ?> m) {
                    Map<String, Object> rule = new LinkedHashMap<>((Map<String, Object>) m);
                    Object id = rule.get("id");
                    if (id != null && !String.valueOf(id).isBlank()) {
                        byId.put(String.valueOf(id), rule);
                    }
                }
            }
        }
        Path override = dataDir.resolve("config/alert-rules.json");
        Map<String, Object> overDoc = readMap(override);
        if (overDoc != null && overDoc.get("rules") instanceof List<?> raw) {
            for (Object o : raw) {
                if (!(o instanceof Map<?, ?> m)) {
                    continue;
                }
                Object id = m.get("id");
                if (id == null) {
                    continue;
                }
                String rid = String.valueOf(id);
                Map<String, Object> existing = byId.get(rid);
                if (existing == null) {
                    byId.put(rid, new LinkedHashMap<>((Map<String, Object>) m));
                } else {
                    existing.putAll((Map<String, Object>) m);
                }
            }
        }
        return new ArrayList<>(byId.values());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readMap(Path path) {
        if (!Files.isRegularFile(path)) {
            return null;
        }
        try {
            return MAPPER.readValue(Files.readString(path), Map.class);
        } catch (IOException | ClassCastException e) {
            return null;
        }
    }
}
