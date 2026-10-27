package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 内置身份注册表（P1 二期，D2/D15）— python
 * {@code lib.infra.builtin_identities} 的 java 对等实现。
 *
 * <p>SoT：{@code shared/config/mailbus/builtin-identities.json}（seed）+
 * {@code {dataDir}/config/builtin-identities.json}（用户改名覆盖）——双栈同一真源。
 * 身份 id/role 稳定；display_name 可改；清单可枚举扩展（本期无权限体系）。
 */
public class BuiltinIdentitiesService {

    private final Path seedPath;
    private final Path overridePath;

    public BuiltinIdentitiesService(Path dataDir, Path mailbusRoot) {
        this.seedPath = mailbusRoot.resolve("config/mailbus/builtin-identities.json");
        this.overridePath = dataDir.resolve("config/builtin-identities.json");
    }

    /** GET /api/identities — 清单（seed 为锚，覆盖文件字段合并）。 */
    public Map<String, Object> list() {
        List<Map<String, Object>> identities = new ArrayList<>();
        Map<String, Map<String, Object>> byId = readEntries(seedPath);
        for (Map<String, Object> ov : readEntries(overridePath).values()) {
            Map<String, Object> base = byId.get(String.valueOf(ov.get("id")));
            if (base != null) {
                base.putAll(ov);
            }
        }
        byId.values().stream()
                .sorted((a, b) -> String.valueOf(a.get("id")).compareTo(String.valueOf(b.get("id"))))
                .forEach(identities::add);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("identities", identities);
        out.put("total", identities.size());
        return out;
    }

    /** PATCH /api/identities/{id} — 改显示名；未知身份或空名返回 null。 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> rename(String identId, String displayName) {
        String name = displayName == null ? "" : displayName.trim();
        if (name.isEmpty() || !readEntries(seedPath).containsKey(identId)) {
            return null;
        }
        try {
            Map<String, Object> doc = Files.isRegularFile(overridePath)
                    ? (Map<String, Object>) readTree(Files.readString(overridePath))
                    : new LinkedHashMap<>();
            List<Map<String, Object>> entries = (List<Map<String, Object>>) (Object)
                    ((List<?>) doc.computeIfAbsent("identities", k -> new ArrayList<>()));
            Map<String, Object> hit = null;
            for (Map<String, Object> e : entries) {
                if (identId.equals(String.valueOf(e.get("id")))) {
                    hit = e;
                    break;
                }
            }
            if (hit == null) {
                hit = new LinkedHashMap<>();
                hit.put("id", identId);
                entries.add(hit);
            }
            hit.put("display_name", name);
            Files.createDirectories(overridePath.getParent());
            Files.writeString(overridePath, toJson(doc));
        } catch (IOException e) {
            return null;
        }
        for (Map<String, Object> ident : ((List<Map<String, Object>>) (Object) (List<?>) list().get("identities"))) {
            if (identId.equals(String.valueOf(ident.get("id")))) {
                return ident;
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Map<String, Object>> readEntries(Path path) {
        if (!Files.isRegularFile(path)) {
            return Map.of();
        }
        try {
            Map<String, Object> doc = (Map<String, Object>) readTree(Files.readString(path));
            Map<String, Map<String, Object>> byId = new LinkedHashMap<>();
            for (Object o : (List<?>) doc.getOrDefault("identities", List.of())) {
                if (o instanceof Map<?, ?> m) {
                    byId.put(String.valueOf(m.get("id")), new LinkedHashMap<>((Map<String, Object>) m));
                }
            }
            return byId;
        } catch (IOException | ClassCastException e) {
            return Map.of();
        }
    }

    private Object readTree(String json) throws IOException {
        return new com.fasterxml.jackson.databind.ObjectMapper().readValue(
                json, java.util.Map.class);
    }

    private String toJson(Object doc) throws IOException {
        return new com.fasterxml.jackson.databind.ObjectMapper()
                .writerWithDefaultPrettyPrinter().writeValueAsString(doc);
    }
}
