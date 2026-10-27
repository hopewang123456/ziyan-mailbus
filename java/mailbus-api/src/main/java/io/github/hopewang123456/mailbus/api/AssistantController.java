package io.github.hopewang123456.mailbus.api;

import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * AI 助手端点（P2 收尾，D10）— python /api/assistant/ask 的 java 对等。
 *
 * <p>双态：boot 层 assistantService bean 存在（ChatClient 装配就位）→ 经反射调
 * askToMap（api 层不 import boot，分层守卫）；否则显式 501，协议与 python 对等可探测。
 */
@RestController
public class AssistantController {

    private final ApplicationContext ctx;

    public AssistantController(ApplicationContext ctx) {
        this.ctx = ctx;
    }

    @PostMapping("/api/assistant/ask")
    public ResponseEntity<Map<String, Object>> ask(@RequestBody Map<String, String> body) {
        String question = body.getOrDefault("question", "").trim();
        if (question.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("status", "error", "error", "missing question"));
        }
        try {
            Object svc = ctx.getBean("assistantService");
            var m = svc.getClass().getMethod("askToMap", String.class);
            @SuppressWarnings("unchecked")
            Map<String, Object> out = (Map<String, Object>) m.invoke(svc, question);
            if ("not_configured".equals(out.get("error"))) {
                return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED).body(out);
            }
            return ResponseEntity.ok(out);
        } catch (Exception e) {
            Throwable cause = e.getCause() != null ? e.getCause() : e;
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(Map.of(
                    "status", "error", "error", "llm_unavailable",
                    "message", String.valueOf(cause.getMessage())));
        }
    }
}
