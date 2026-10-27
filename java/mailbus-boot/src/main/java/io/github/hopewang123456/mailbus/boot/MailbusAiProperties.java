package io.github.hopewang123456.mailbus.boot;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * L3 装配开关（D7/D8 的 java/Spring 表达，P0c）：
 * 行为参数与实现选择全部声明式配置驱动，代码只提供实现类。
 *
 * <pre>
 * mailbus:
 *   ai:
 *     enabled: false   # true 时 AI 助手/指标问答装配激活（需 provider starter）
 *     provider: ""     # P2 选型后填写（openai/deepseek/ollama…）
 *     model: ""        # 默认模型名
 * </pre>
 */
@ConfigurationProperties(prefix = "mailbus.ai")
public record MailbusAiProperties(boolean enabled, String provider, String model) {

    public MailbusAiProperties {
        provider = provider == null ? "" : provider;
        model = model == null ? "" : model;
    }
}
