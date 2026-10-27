package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator;
import io.github.hopewang123456.mailbus.app.MetricsManifestService;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Map;

/**
 * mailbus 指标 → Micrometer 注册（P2 java 侧 D8 差异化）。
 *
 * <p>值计算在 {@link MailbusMetricsCalculator}（app 层，REST 查询共用）；
 * 本类只做 Micrometer 装配：每个 manifest 指标注册 Gauge
 * {@code mailbus.<id>}（无源指标 NaN——Micrometer 无数据惯例）。
 * 红利：{@code /actuator/metrics/mailbus.<id>} 标准化可查（python 侧无此通道）。
 */
public class MailbusMetricsBinder implements MeterBinder {

    private final MetricsManifestService manifest;
    private final MailbusMetricsCalculator calculator;

    public MailbusMetricsBinder(MetricsManifestService manifest, MailbusMetricsCalculator calculator) {
        this.manifest = manifest;
        this.calculator = calculator;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        for (Map<String, Object> m : manifest.metrics()) {
            String id = String.valueOf(m.get("id"));
            Object nameZh = m.get("name") instanceof Map<?, ?> nm ? nm.get("zh") : null;
            Gauge.builder("mailbus." + id, () -> gaugeValue(id))
                    .description(String.valueOf(nameZh != null ? nameZh : id))
                    .register(registry);
        }
    }

    private double gaugeValue(String metricId) {
        Double v = calculator.currentValue(metricId);
        return v == null ? Double.NaN : v;
    }
}
