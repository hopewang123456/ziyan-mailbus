package io.github.hopewang123456.mailbus.app;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2c 规划器 — tier0 规则表 / constraints / S 级修剪 / LLM 防幻觉
 * （python router/planner.py 对等）。
 */
class TaskPlannerServiceTest {

    @TempDir
    Path dataDir;

    private TaskPlannerService rulesOnly;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {"1": {}, "4": {}, "5": {}, "6": {}, "8": {}, "12": {}}}
                """);
        rulesOnly = new TaskPlannerService(dataDir, null);
    }

    private Map<String, Object> auto(String taskType, String tier, Map<String, Object> constraints) {
        Map<String, Object> env = new java.util.LinkedHashMap<>();
        env.put("mode", "auto");
        env.put("intent", "做点东西");
        env.put("task_type", taskType);
        env.put("tier", tier);
        if (constraints != null) {
            env.put("constraints", constraints);
        }
        return env;
    }

    @Test
    void tier0RuleHits() {
        Map<String, Object> out = rulesOnly.plan(auto("feature", "M", null));
        List<?> chain = (List<?>) out.get("planned_chain");
        assertEquals(1, chain.size());
        assertEquals(1, ((Number) ((Map<?, ?>) chain.get(0)).get("role_type")).intValue());
        assertEquals("rules", ((Map<?, ?>) out.get("plan_meta")).get("method"));
        assertEquals(1.0, ((Number) ((Map<?, ?>) out.get("plan_meta")).get("confidence")).doubleValue());
    }

    @Test
    void constraintsRequiredAndForbidden() {
        Map<String, Object> out = rulesOnly.plan(auto("bugfix", "M",
                Map.of("required_role_types", List.of(4), "forbidden_role_types", List.of(12))));
        List<Integer> chain = ((List<?>) out.get("planned_chain")).stream()
                .map(s -> ((Number) ((Map<?, ?>) s).get("role_type")).intValue()).toList();
        assertEquals(List.of(4, 8, 5), chain); // required 前插 4；forbidden 删 12
    }

    @Test
    void tierSBugfixTrimsRoleSix() {
        Map<String, Object> out = rulesOnly.plan(auto("bugfix", "S",
                Map.of("required_role_types", List.of(6))));
        List<Integer> chain = ((List<?>) out.get("planned_chain")).stream()
                .map(s -> ((Number) ((Map<?, ?>) s).get("role_type")).intValue()).toList();
        assertEquals(List.of(8, 5, 12), chain); // 6 被 S 级修剪
    }

    @Test
    void unknownTypeWithoutLlmFails() {
        TaskPlannerService.PlanError e = assertThrows(TaskPlannerService.PlanError.class,
                () -> rulesOnly.plan(auto("custom-unknown", "M", null)));
        assertEquals("plan_failed", e.code);
    }

    @Test
    void llmOutputFilteredAgainstValidRoleTypes() {
        TaskPlannerService llm = new TaskPlannerService(dataDir, (system, user) ->
                """
                {"planned_chain":[{"role_type":8,"reason":"开发"},{"role_type":99,"reason":"幻觉"}],
                 "plan_meta":{"method":"internal_llm","task_type_guess":"custom","confidence":0.7,
                              "provider_used":"local","model":"test"}}
                """);
        Map<String, Object> out = llm.plan(auto("custom-thing", "M", null));
        List<?> chain = (List<?>) out.get("planned_chain");
        assertEquals(1, chain.size()); // role_type 99 被防幻觉过滤
        assertEquals(8, ((Number) ((Map<?, ?>) chain.get(0)).get("role_type")).intValue());
        assertEquals("internal_llm", ((Map<?, ?>) out.get("plan_meta")).get("method"));
    }

    @Test
    void llmFailureRaisesLlmError() {
        TaskPlannerService llm = new TaskPlannerService(dataDir, (s, u) -> {
            throw new IllegalStateException("connection refused");
        });
        assertThrows(TaskPlannerService.LlmError.class,
                () -> llm.plan(auto("custom-thing", "M", null)));
    }
}
