package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator;
import io.github.hopewang123456.mailbus.app.MetricsManifestService;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 指标端点（P2 B1/B2 对等 python /api/metrics/{manifest,query} 同协议）。
 *
 * <p>差异（D8）：值走 app 层 {@link MailbusMetricsCalculator} 现算；
 * Micrometer/actuator 暴露为 boot 层附加通道。M1 无数据源指标返回
 * error: no_source_in_m1（不静默 0）；1h 窗口随 M2 时序落地。
 */
@RestController
public class MetricsController {

    private final MetricsManifestService manifest;
    private final MailbusMetricsCalculator calculator;

    public MetricsController(Environment env, MailbusMetricsCalculator calculator) {
        this.manifest = new MetricsManifestService(
                io.github.hopewang123456.mailbus.app.SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir")),
                io.github.hopewang123456.mailbus.app.SharedRoots.resolve(env.getProperty("mailbus.root")));
        this.calculator = calculator;
    }

    @GetMapping("/api/metrics/manifest")
    public Map<String, Object> manifest() {
        return Map.of("status", "ok",
                "manifest", Map.of("schema", "mailbus-metrics-manifest-v1",
                        "metrics", manifest.metrics()));
    }

    @GetMapping("/api/metrics/query")
    public Map<String, Object> query(@RequestParam(required = false) String metric,
                                     @RequestParam(defaultValue = "point") String granularity) {
        if (!"point".equals(granularity)) {
            return Map.of("status", "error", "error", "granularity_not_supported_yet");
        }
        List<Map<String, Object>> points = new ArrayList<>();
        for (Map<String, Object> m : manifest.metrics()) {
            String id = String.valueOf(m.get("id"));
            if (metric != null && !metric.isBlank() && !metric.equals(id)) {
                continue;
            }
            Map<String, Object> p = new LinkedHashMap<>();
            p.put("metric", id);
            if (calculator.hasSource(id)) {
                Double v = calculator.currentValue(id);
                if (v != null) {
                    p.put("value", v);
                    p.put("unit", m.getOrDefault("unit", "count"));
                } else {
                    p.put("error", "no_source_in_m1");
                }
            } else {
                p.put("error", "no_source_in_m1");
            }
            points.add(p);
        }
        if (metric != null && !metric.isBlank() && points.isEmpty()) {
            return Map.of("status", "error", "error", "unknown_metric", "metric", metric);
        }
        return Map.of("status", "ok", "points", points);
    }
}
