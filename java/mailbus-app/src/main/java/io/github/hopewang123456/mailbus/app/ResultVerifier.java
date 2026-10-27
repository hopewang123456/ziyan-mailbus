package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/**
 * 步骤产出验证 — python {@code ops/verify/step_verify.py verify_step_result}
 * 对等（M2b 字段校验层）。git diff / pytest / 交付物矩阵钩子不做
 * （python 默认亦多关闭，生态差异，记 M2b 偏差）。
 */
public class ResultVerifier {

    private final Path dataDir;

    public ResultVerifier(Path dataDir) {
        this.dataDir = dataDir;
    }

    /** strict 开关（config.mailbus_automation.verify.strict）。 */
    public boolean strict() {
        Map<String, Object> config = JsonFiles.readMap(dataDir.resolve("config.json"));
        if (config == null) {
            return false;
        }
        Object auto = config.get("mailbus_automation");
        if (auto instanceof Map<?, ?> m && m.get("verify") instanceof Map<?, ?> v) {
            return Boolean.TRUE.equals(v.get("strict"));
        }
        return false;
    }

    /** 返回 null = 通过；否则失败原因。 */
    public String verifyStepResult(Integer roleType, String conclusion, Map<String, Object> result) {
        boolean strict = strict();
        String c = str(conclusion).toLowerCase();
        Map<String, Object> details = detailsOf(result);

        if (roleType != null && roleType == 8 && (c.equals("done") || c.equals("pass"))) {
            return verifyDevDone(details, strict);
        }
        if (roleType != null && roleType == 6 && c.equals("pass")) {
            return verifyTestDone(details, strict);
        }
        if (roleType != null && roleType == 9 && c.equals("dispatched")) {
            Object nxt = firstNonEmpty(details.get("next_assignee"), details.get("dispatched_to"));
            if ((nxt == null || String.valueOf(nxt).isEmpty()) && strict) {
                return "missing dispatch target";
            }
        }
        return null;
    }

    private String verifyDevDone(Map<String, Object> d, boolean strict) {
        if ("fail".equals(str(d.get("self_test")))) {
            return "self_test failed";
        }
        if (strict) {
            boolean evidence = d.get("files_changed") != null
                    || d.get("git_diff_stat") != null
                    || d.get("deliverable") != null;
            if (!evidence) {
                return "no deliverable or diff evidence";
            }
        }
        String st = str(d.get("self_test"));
        boolean knownState = st.isEmpty() || "pass".equals(st) || "skip".equals(st);
        if (!knownState && d.get("deliverable") == null) {
            return "missing deliverable";
        }
        return null;
    }

    private String verifyTestDone(Map<String, Object> d, boolean strict) {
        Object results = d.get("results");
        if (results == null && strict) {
            return "missing test results";
        }
        if (results instanceof List<?> list) {
            long failed = list.stream()
                    .filter(r -> r instanceof Map<?, ?> m)
                    .map(r -> str(((Map<?, ?>) r).get("status")).toLowerCase())
                    .filter(s -> s.equals("fail") || s.equals("failed") || s.equals("error"))
                    .count();
            if (failed > 0) {
                return failed + " test case(s) failed in report";
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> detailsOf(Map<String, Object> result) {
        Object details = result.get("details");
        if (details instanceof Map<?, ?> m) {
            Map<String, Object> merged = new java.util.LinkedHashMap<>((Map<String, Object>) m);
            merged.putIfAbsent("summary", result.get("summary"));
            return merged;
        }
        return result;
    }

    private static Object firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return v;
            }
        }
        return null;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
