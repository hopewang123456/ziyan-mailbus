package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * metrics manifest 读取（P2 B1 双栈同源）— python `lib.adapters.metrics.manifest`
 * 的 java 对等：同一份 {@code shared/config/mailbus/metrics-manifest.json}，
 * 指标 id/口径/维度两侧唯一真源。
 *
 * <p>优先级与 python 一致：store 覆盖（{dataDir}/config/metrics-manifest.json）
 * → shared seed。
 */
public class MetricsManifestService {

    private final Path seedPath;
    private final Path overridePath;

    public MetricsManifestService(Path dataDir, Path mailbusRoot) {
        this.seedPath = mailbusRoot.resolve("config/mailbus/metrics-manifest.json");
        this.overridePath = dataDir.resolve("config/metrics-manifest.json");
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> metrics() {
        Map<String, Object> doc = readDoc(overridePath);
        if (doc == null || !(doc.get("metrics") instanceof List)) {
            doc = readDoc(seedPath);
        }
        if (doc == null || !(doc.get("metrics") instanceof List<?> raw)) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object o : raw) {
            if (o instanceof Map<?, ?> m) {
                out.add((Map<String, Object>) m);
            }
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readDoc(Path path) {
        if (!Files.isRegularFile(path)) {
            return null;
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(Files.readString(path), Map.class);
        } catch (IOException | ClassCastException e) {
            return null;
        }
    }
}
