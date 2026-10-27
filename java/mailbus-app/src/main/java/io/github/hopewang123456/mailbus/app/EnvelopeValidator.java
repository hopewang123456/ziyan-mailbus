package io.github.hopewang123456.mailbus.app;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * POST /api/tasks/create 的 envelope 校验 — python
 * {@code router/envelope_validate.py} 对等（M2a；planned 条目只收 role_type，
 * station 变体记 M2b+ 偏差）。
 */
public class EnvelopeValidator {

    private static final Pattern TASK_ID = Pattern.compile("^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$");
    private static final Set<String> LEGACY_KEYS = Set.of("title", "assignee", "steps", "pipeline");

    /** python is_legacy_create_body：含 legacy 键且无 intent → 410。 */
    public boolean isLegacyCreateBody(Map<String, Object> body) {
        if (body == null) {
            return true;
        }
        boolean hasLegacy = LEGACY_KEYS.stream().anyMatch(body::containsKey);
        return hasLegacy && !body.containsKey("intent");
    }

    /** 校验错误清单（空 = 通过）。与 python validate_envelope 同序同文案。 */
    public List<String> validate(Map<String, Object> body) {
        List<String> errors = new ArrayList<>();
        if (body == null) {
            errors.add("body must be object");
            return errors;
        }
        for (String field : List.of("task_id", "intent", "initiator", "mode", "tier")) {
            if (!body.containsKey(field)) {
                errors.add("missing " + field);
            }
        }
        String tid = str(body.get("task_id"));
        if (!tid.isEmpty() && !TASK_ID.matcher(tid).matches()) {
            errors.add("invalid task_id format");
        }
        String mode = str(body.get("mode"));
        if (!"explicit".equals(mode) && !"auto".equals(mode)) {
            errors.add("mode must be explicit or auto");
        }
        if ("explicit".equals(mode)) {
            Object planned = body.get("planned_chain");
            if (!(planned instanceof List<?> list) || list.isEmpty()) {
                errors.add("explicit mode requires planned_chain");
            } else {
                for (int i = 0; i < list.size(); i++) {
                    if (!(list.get(i) instanceof Map<?, ?> step) || step.get("role_type") == null) {
                        errors.add("planned_chain[" + i + "] missing role_type/station");
                    }
                }
            }
        }
        String tier = str(body.get("tier"));
        if (!tier.isEmpty() && !List.of("S", "M", "L").contains(tier)) {
            errors.add("tier must be S, M, or L");
        }
        return errors;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
