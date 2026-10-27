package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.app.DocsRagService;
import io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator;
import io.github.hopewang123456.mailbus.app.MetricsManifestService;
import org.springframework.ai.chat.client.ChatClient;

import java.util.List;

/**
 * java AI 助手（P2 收尾，D10 对等）— python /api/assistant/ask 的真实现。
 *
 * <p>三源上下文与 python 同构：① 指标语义层注入（B6：只念 calculator 真值）
 * ② docs RAG 片段（同一知识库目录）③ 用户问题；经 {@link ChatClient} 生成。
 * ChatClient bean 由 {@link AiConfig} 双条件装配（enabled + provider 就位）。
 */
public class AssistantService {

    private final org.springframework.beans.factory.ObjectProvider<org.springframework.ai.chat.model.ChatModel> chatModelProvider;
    private final DocsRagService rag;
    private final MetricsManifestService manifest;
    private final MailbusMetricsCalculator calculator;

    public AssistantService(org.springframework.beans.factory.ObjectProvider<org.springframework.ai.chat.model.ChatModel> chatModel,
                            DocsRagService rag,
                            MetricsManifestService manifest,
                            MailbusMetricsCalculator calculator) {
        this.chatModelProvider = chatModel;
        this.rag = rag;
        this.manifest = manifest;
        this.calculator = calculator;
    }

    /** ChatClient 是否就位（装配期不判——@ConditionalOnBean 在用户配置类上不可靠，调用期判空）。 */
    public boolean available() {
        return chatModelProvider.getIfAvailable() != null;
    }

    public record Answer(String answer, List<DocsRagService.Citation> citations) {}

    public Answer ask(String question) {
        org.springframework.ai.chat.model.ChatModel chatModel = chatModelProvider.getIfAvailable();
        if (chatModel == null) {
            throw new IllegalStateException("not_configured: ChatModel 未装配");
        }
        ChatClient chat = ChatClient.builder(chatModel).build();
        List<DocsRagService.Citation> citations = rag.retrieve(question);
        StringBuilder ragBlock = new StringBuilder();
        for (DocsRagService.Citation c : citations) {
            ragBlock.append("[").append(c.sourceId()).append("/").append(c.title()).append("] ")
                    .append(c.excerpt()).append("\n");
        }
        if (ragBlock.isEmpty()) {
            ragBlock.append("（无手册命中）");
        }

        String system = """
                你是 mailbus 的内置 AI 助手（子言的参谋）。回答用户关于 mailbus 系统的问题：
                - 涉及指标/系统状态时，仅依据下方「当前指标」块作答，不要编造数字；
                - 涉及操作/架构时，优先引用「手册片段」，注明来源（source/title）；
                - 手册与指标都没有答案时，明确说不知道并建议查看哪个 runbook；
                - 用中文，简洁，先给结论。

                【当前指标】
                %s

                【手册片段】
                %s""".formatted(DocsRagService.metricsContext(manifest, calculator), ragBlock);

        String answer = chat.prompt()
                .system(system)
                .user(question)
                .call()
                .content();
        return new Answer(String.valueOf(answer), citations);
    }

    /** REST 协议形（api 层经反射调用，避免 api→boot 分层违规）。 */
    public java.util.Map<String, Object> askToMap(String question) {
        if (!available()) {
            return java.util.Map.of("status", "error", "error", "not_configured",
                    "message", "ChatClient 未装配（mailbus.ai.enabled + provider）");
        }
        Answer a = ask(question);
        return java.util.Map.of(
                "status", "ok",
                "answer", a.answer(),
                "citations", a.citations().stream()
                        .map(c -> java.util.Map.of("source_id", c.sourceId(), "title", c.title()))
                        .toList());
    }
}
