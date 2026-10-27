package io.github.hopewang123456.mailbus.boot;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI 条件装配地基（P0c，D10/D12）。
 *
 * 双重条件：{@code mailbus.ai.enabled=true}（用户开关）且 classpath 存在
 * {@link ChatModel}（provider starter 就位，P2 智能层选型后引入）才装配
 * {@link ChatClient}。此前零 AI bean、零额外启动开销——L3「配置驱动装配」
 * 的 java 侧范式，后续指标问答 / AI 助手 RAG 均沿用本模式接入。
 */
@Configuration
@EnableConfigurationProperties(MailbusAiProperties.class)
@ConditionalOnProperty(prefix = "mailbus.ai", name = "enabled", havingValue = "true")
public class AiConfig {

    @Bean
    @ConditionalOnBean(ChatModel.class)
    public ChatClient chatClient(ChatModel chatModel, MailbusAiProperties props) {
        ChatClient.Builder builder = ChatClient.builder(chatModel);
        if (!props.model().isBlank()) {
            // Spring AI 2.0: defaultOptions 接收 ChatOptions.Builder 本身
            builder.defaultOptions(
                    org.springframework.ai.chat.prompt.ChatOptions.builder()
                            .model(props.model()));
        }
        return builder.build();
    }
}
