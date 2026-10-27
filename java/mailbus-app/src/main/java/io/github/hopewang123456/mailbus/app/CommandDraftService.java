package io.github.hopewang123456.mailbus.app;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 发令草稿预演 — python {@code handle_command_draft} 对等（M2c，D4 草稿确认制）：
 * 无副作用走 plan_task（tier0 规则优先→LLM），防幻觉过滤，显式报错不静默降级。
 */
public class CommandDraftService {

    private final TaskPlannerService planner;

    public CommandDraftService(TaskPlannerService planner) {
        this.planner = planner;
    }

    /** 返回 {status, body}（http 状态码在 status）。 */
    public Map<String, Object> draft(String intent, String taskType, String tier) {
        if (intent == null || intent.isBlank()) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", "fatal");
            b.put("detail", "缺少 intent（需求描述）");
            return Map.of("status", 400, "body", b);
        }
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("task_id", "draft-");
        envelope.put("intent", intent.strip());
        envelope.put("initiator", "ziyan");
        envelope.put("task_type", (taskType == null || taskType.isBlank() ? "custom" : taskType).toLowerCase());
        envelope.put("tier", tier == null || tier.isBlank() ? "M" : tier);
        envelope.put("mode", "auto");

        Map<String, Object> planned;
        try {
            planned = planner.plan(envelope);
        } catch (TaskPlannerService.LlmError e) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", "llm_error");
            b.put("message", String.valueOf(e.getMessage()));
            return Map.of("status", 503, "body", b);
        } catch (TaskPlannerService.PlanError e) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", e.code);
            b.put("message", String.valueOf(e.getMessage()));
            return Map.of("status", 422, "body", b);
        }

        Object chainObj = planned.get("planned_chain");
        List<?> chain = chainObj instanceof List<?> l ? l : List.of();
        List<Integer> valid = planner.validRoleTypes();
        List<Map<String, Object>> filtered = new java.util.ArrayList<>();
        for (Object o : chain) {
            if (o instanceof Map<?, ?> step) {
                int rt = step.get("role_type") == null ? -1
                        : Integer.parseInt(String.valueOf(((Number) step.get("role_type")).intValue()));
                if (valid.contains(rt)) {
                    filtered.add(new LinkedHashMap<>((Map<String, Object>) step));
                }
            }
        }
        if (filtered.isEmpty()) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", "draft_empty");
            b.put("message", "草稿为空（LLM 输出未含有效职位）");
            return Map.of("status", 422, "body", b);
        }
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("planned_chain", filtered);
        draft.put("plan_meta", planned.getOrDefault("plan_meta", Map.of()));
        draft.put("intent", envelope.get("intent"));
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("status", "ok");
        b.put("draft", draft);
        return Map.of("status", 200, "body", b);
    }
}
