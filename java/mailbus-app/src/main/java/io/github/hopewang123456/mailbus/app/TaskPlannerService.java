package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 任务规划器 — python {@code router/planner.py plan_task} 对等（M2c）：
 * Tier-0 规则表（task_type → role_type 链）优先，未命中走 LLM（可注入回调，
 * Spring AI ChatModel 在 boot 装配；未配置即 plan_failed，不静默降级）。
 *
 * <p>偏差：planner RAG 简化为 role-types 目录注入（python 走 runbooks RAG）；
 * code_review harness 特判链不做（harness extensions 属 M2c+）。
 */
public class TaskPlannerService {

    /** SoT: tier0-planner-spec.md §2（与 python 同表）。 */
    static final Map<String, List<Integer>> TIER0_RULES = Map.ofEntries(
            Map.entry("bugfix", List.of(8, 5, 12)),
            Map.entry("code_review", List.of(5, 12)),
            Map.entry("spike", List.of(3, 1, 9)),
            Map.entry("doc", List.of(1, 9)),
            Map.entry("security_review", List.of(2, 5, 9)),
            Map.entry("ops", List.of(7, 9)),
            Map.entry("video_publish", List.of(3)),
            Map.entry("intake", List.of(4)),
            Map.entry("feature", List.of(1)),
            Map.entry("finance", List.of(10)),
            Map.entry("full_delivery", List.of(1, 3, 1, 9, 8, 8, 2, 5, 6, 7, 11, 12)));

    /** LLM 补全回调（system+user → JSON 文本）；boot 层用 Spring AI ChatModel 实现。 */
    public interface LlmClient {
        String complete(String system, String user);
    }

    /** python PlanError 对等。 */
    public static class PlanError extends RuntimeException {
        public final String code;

        public PlanError(String code, String message) {
            super(message == null || message.isEmpty() ? code : message);
            this.code = code;
        }
    }

    private final Path dataDir;
    private final LlmClient llm;

    public TaskPlannerService(Path dataDir, LlmClient llm) {
        this.dataDir = dataDir;
        this.llm = llm;
    }

    /** 返回 a2a-planner-output 形状：{planned_chain:[{role_type,reason}], plan_meta}。 */
    public Map<String, Object> plan(Map<String, Object> envelope) {
        String mode = str(envelope.get("mode"));
        String taskType = str(envelope.getOrDefault("task_type", "unknown")).toLowerCase();
        String tier = str(envelope.getOrDefault("tier", "M"));
        Map<String, Object> constraints = envelope.get("constraints") instanceof Map<?, ?> c
                ? toMap(c) : Map.of();

        if ("explicit".equals(mode)) {
            return explicitPlan(envelope, taskType);
        }

        List<Integer> chain = TIER0_RULES.get(taskType);
        if (chain != null) {
            chain = applyConstraints(chain, constraints);
            chain = trimTierSBugfix(chain, tier, taskType);
            if (!chain.isEmpty()) {
                return rulesOut(chain, taskType);
            }
        }
        return llmPlan(envelope, taskType, tier, constraints);
    }

    private Map<String, Object> explicitPlan(Map<String, Object> envelope, String taskType) {
        Object plannedObj = envelope.get("planned_chain");
        if (!(plannedObj instanceof List<?> planned) || planned.isEmpty()) {
            throw new PlanError("schema_invalid", "explicit mode requires planned_chain");
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object o : planned) {
            if (!(o instanceof Map<?, ?> x) || x.get("role_type") == null) {
                throw new PlanError("schema_invalid", "planned_chain entry missing role_type/station");
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("role_type", intOr(x.get("role_type"), 0));
            item.put("reason", str(x.get("reason")));
            if (x.get("pin_agent") != null) {
                item.put("pin_agent", str(x.get("pin_agent")));
            }
            out.add(item);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("planned_chain", out);
        result.put("plan_meta", meta("rules", taskType, 1.0, "rules", null));
        return result;
    }

    private Map<String, Object> llmPlan(Map<String, Object> envelope, String taskType,
                                        String tier, Map<String, Object> constraints) {
        if (llm == null) {
            throw new PlanError("plan_failed",
                    "no tier0 rule for task_type '" + taskType + "' and LLM planner not configured");
        }
        String intent = str(envelope.get("intent"));
        String system = """
                You are mailbus Tier-1 task planner. Output ONLY valid JSON matching:
                {"planned_chain":[{"role_type":int,"reason":str}...],
                "plan_meta":{"method":"internal_llm","task_type_guess":str,
                "confidence":0-1,"provider_used":"local|remote","model":str}}
                Use role_type integers from the role catalog. Max 12 steps.""";
        String user = "intent: " + intent + "\ntier: " + tier + "\ntask_type: " + taskType
                + "\nconstraints: " + constraints + "\n\nRole catalog (role_type: name):\n"
                + roleCatalogText();

        String raw;
        try {
            raw = llm.complete(system, user);
        } catch (RuntimeException e) {
            throw new LlmError(str(e.getMessage()));
        }
        Map<String, Object> parsed = parseJsonLoose(raw);
        if (parsed == null) {
            throw new LlmError("llm output is not valid JSON");
        }
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> chainRaw = parsed.get("planned_chain") instanceof List<?> l
                ? (List<Map<String, Object>>) (List<?>) l : List.of();
        // 防幻觉：role_type 全量过滤（B6 精神——LLM 只翻译，口径由语义层把关）
        List<Integer> valid = validRoleTypes();
        List<Map<String, Object>> chainOut = new ArrayList<>();
        for (Map<String, Object> step : chainRaw) {
            int rt = intOr(step.get("role_type"), -1);
            if (valid.contains(rt)) {
                chainOut.add(step);
            }
        }
        List<Integer> chain = new ArrayList<>();
        for (Map<String, Object> s : chainOut) {
            chain.add(intOr(s.get("role_type"), 0));
        }
        chain = applyConstraints(chain, constraints);
        Map<String, Object> metaIn = parsed.get("plan_meta") instanceof Map<?, ?> m ? toMap(m) : new LinkedHashMap<>();
        String guess = str(metaIn.getOrDefault("task_type_guess", taskType));
        chain = trimTierSBugfix(chain, tier, guess);
        if (chainOut.isEmpty() || chain.isEmpty()) {
            throw new PlanError("plan_failed", "llm output has no valid role_type");
        }
        // 以过滤后的链重建 planned_chain（保持 reason）
        List<Map<String, Object>> filtered = new ArrayList<>();
        for (Integer rt : chain) {
            Map<String, Object> step = new LinkedHashMap<>();
            step.put("role_type", rt);
            step.put("reason", chainOut.stream().filter(s -> intOr(s.get("role_type"), -1) == rt)
                    .map(s -> str(s.get("reason"))).findFirst().orElse(""));
            filtered.add(step);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("planned_chain", filtered);
        Map<String, Object> meta = meta("internal_llm", guess,
                doubleOr(metaIn.get("confidence"), 0.5), "spring_ai",
                str(metaIn.getOrDefault("model", "internal_llm")));
        result.put("plan_meta", meta);
        return result;
    }

    /** LLM 调用层异常（draft 端点映射 503）。 */
    public static class LlmError extends RuntimeException {
        public LlmError(String message) {
            super(message);
        }
    }

    // ── 规则工具（与 python 同语义）─────────────────────────────────────────

    static List<Integer> applyConstraints(List<Integer> chain, Map<String, Object> constraints) {
        List<Integer> out = new ArrayList<>(chain);
        Object required = constraints.get("required_role_types");
        if (required instanceof List<?> list) {
            for (Object o : list) {
                int rt = intOr(o, -1);
                if (rt > 0 && !out.contains(rt)) {
                    out.add(0, rt);
                }
            }
        }
        Object forbidden = constraints.get("forbidden_role_types");
        if (forbidden instanceof List<?> list) {
            for (Object o : list) {
                out.remove(Integer.valueOf(intOr(o, -1)));
            }
        }
        return out;
    }

    static List<Integer> trimTierSBugfix(List<Integer> chain, String tier, String taskType) {
        if ("S".equals(tier) && "bugfix".equals(taskType) && chain.contains(6)) {
            List<Integer> out = new ArrayList<>(chain);
            out.remove(Integer.valueOf(6));
            return out;
        }
        return chain;
    }

    private Map<String, Object> rulesOut(List<Integer> chain, String taskType) {
        List<Map<String, Object>> planned = new ArrayList<>();
        for (int rt : chain) {
            planned.add(Map.of("role_type", rt, "reason", "tier0 " + taskType + " → role_type " + rt));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("planned_chain", planned);
        result.put("plan_meta", meta("rules", taskType, 1.0, "rules", null));
        return result;
    }

    private static Map<String, Object> meta(String method, String guess, double confidence,
                                            String provider, String model) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("method", method);
        m.put("task_type_guess", guess);
        m.put("confidence", confidence);
        m.put("provider_used", provider);
        if (model != null) {
            m.put("model", model);
        }
        return m;
    }

    /** role-types.json 全量合法 role_type（防幻觉白名单）。 */
    public List<Integer> validRoleTypes() {
        var root = JsonFiles.readTree(dataDir.resolve("roles/json/role-types.json"));
        List<Integer> out = new ArrayList<>();
        if (root != null) {
            root.path("roles").fieldNames().forEachRemaining(k -> out.add(intOr(k, -1)));
        }
        return out;
    }

    /** LLM 提示词用的职位目录文本（role_type: 中文名）。 */
    private String roleCatalogText() {
        var root = JsonFiles.readTree(dataDir.resolve("roles/json/role-types.json"));
        if (root == null) {
            return "(no role catalog)";
        }
        StringBuilder sb = new StringBuilder();
        root.path("roles").fields().forEachRemaining(e -> {
            String zh = e.getValue().path("display").path("zh").asText("");
            sb.append(e.getKey()).append(": ").append(zh.isEmpty() ? e.getValue().path("key").asText("") : zh)
                    .append('\n');
        });
        return sb.toString();
    }

    private static Map<String, Object> parseJsonLoose(String raw) {
        if (raw == null) {
            return null;
        }
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return null;
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(raw.substring(start, end + 1),
                            new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {
                            });
        } catch (Exception e) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object o) {
        return (Map<String, Object>) o;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static int intOr(Object o, int fallback) {
        if (o instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(o));
        } catch (RuntimeException e) {
            return fallback;
        }
    }

    private static double doubleOr(Object o, double fallback) {
        if (o instanceof Number n) {
            return n.doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(o));
        } catch (RuntimeException e) {
            return fallback;
        }
    }
}
