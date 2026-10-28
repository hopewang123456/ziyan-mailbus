package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.app.SharedRoots;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/**
 * {@code mailbus.data-dir} 启动期一次性规范化（2026-10-28 技术债批次二）。
 *
 * <p>根因（修复前）：同一属性被四条路径以不一致语义消费——JDBC URL 字符串
 * 替换（application.yml）、裸 {@code Path.of}、{@link SharedRoots} 探测、
 * ensureDataDir 建目录。相对路径随启动方式漂移（mvn spring-boot:run 的
 * cwd=模块 basedir、java -jar 的 shell cwd、docker 的 /app），典型症状是
 * 消息索引与任务池分家（split-brain）或「相对路径数据全消失」。
 *
 * <p>本处理器在属性绑定<b>之前</b>把 {@code mailbus.data-dir} 解析为
 * 绝对路径并回写高优先级属性源——这是唯一能覆盖 JDBC URL 占位符替换的层
 * （URL 是纯字符串拼接，任何后置规范化都救不了 yml）。处理顺序：
 * <ol>
 *   <li>读全来源（args/env/yml）的 {@code mailbus.data-dir}（缺省探测，
 *       与 {@link SharedRoots#resolveDataDir} 同序）；</li>
 *   <li>目录不存在则创建（吸收原 ensureDataDir 职责，且看得见 env/yml）；</li>
 *   <li>{@code toAbsolutePath().normalize()} 后以
 *       {@code MapPropertySource} 覆盖回写。</li>
 * </ol>
 *
 * <p>注册：{@code META-INF/spring.factories} 的
 * {@code org.springframework.boot.env.EnvironmentPostProcessor}。
 */
public class DataDirPostProcessor implements EnvironmentPostProcessor {

    static final String PROPERTY = "mailbus.data-dir";
    static final String SOURCE_NAME = "mailbusDataDirCanonical";

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment,
                                       SpringApplication application) {
        String raw = environment.getProperty(PROPERTY);
        Path resolved = resolve(raw);
        if (resolved == null) {
            return; // 无值且探测失败：保持原样，由后续消费点报错
        }
        boolean created = !Files.isDirectory(resolved);
        if (created) {
            // 显式（或探测兜底）路径原本不存在：建目录，但高声提示——
            // 拼错相对路径会得到一份空 store，WARN 让它立刻可见
            System.out.println("[mailbus] WARN: data-dir '" + resolved.toAbsolutePath()
                    + "' did not exist; creating it. If this is unexpected, check"
                    + " the path (mvn spring-boot:run cwd is the module basedir).");
        }
        try {
            Files.createDirectories(resolved);
        } catch (Exception e) {
            System.err.println("[mailbus] WARN: cannot create data-dir " + resolved + ": " + e);
        }
        Path canonical = resolved.toAbsolutePath().normalize();
        environment.getPropertySources().addFirst(new MapPropertySource(
                SOURCE_NAME,
                Map.of(PROPERTY, canonical.toString())));
        System.out.println("[mailbus] data-dir canonicalized: " + raw + " -> " + canonical);
    }

    /** 与 SharedRoots.resolveDataDir 同序解析，但目录不存在时也认（会创建）。 */
    private Path resolve(String raw) {
        if (raw != null && !raw.isBlank()) {
            return Path.of(raw.trim());
        }
        for (String cand : List.of("../shared/store", "../../shared/store",
                "shared/store", "store")) {
            Path p = Path.of(cand);
            if (Files.isDirectory(p)) {
                return p.toAbsolutePath().normalize();
            }
        }
        return null;
    }
}
