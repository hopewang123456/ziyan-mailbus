package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 步骤结果文件 IO 与适用性校验 — python
 * {@code infra/pipeline_results.py} + {@code task_fsm.result_applies_to_step}
 * 对等（M2b）。SoT：{dataDir}/msg-results/{taskId}/step-{sid}.json。
 */
public class StepResultIo {

    /** 视为步骤完成的 conclusion 集合（python _DONE_CONCLUSIONS）。 */
    public static final Set<String> DONE_CONCLUSIONS = Set.of(
            "done", "pass", "approved", "fail", "dispatched", "rejected",
            "need_research", "blocked", "warning",
            "clarifications_needed", "return_to_owner", "needs_clarification");

    /** 阻塞性 conclusion（python _BLOCKING_CONCLUSIONS）。 */
    public static final Set<String> BLOCKING_CONCLUSIONS = Set.of(
            "fail", "rejected", "blocked", "warning");

    private final Path dataDir;

    public StepResultIo(Path dataDir) {
        this.dataDir = dataDir;
    }

    public Path resultPath(String taskId, String stepId) {
        return dataDir.resolve("msg-results").resolve(taskId).resolve("step-" + stepId + ".json");
    }

    /** python write_step_result_file：落盘并补缺省字段。 */
    public Path writeStepResult(String taskId, String stepId, Map<String, Object> result,
                                String agent, Integer roleType, String nowIso) {
        Map<String, Object> payload = new java.util.LinkedHashMap<>(result);
        payload.putIfAbsent("task_id", taskId);
        payload.putIfAbsent("step_id", stepId);
        if (agent != null && !agent.isEmpty()) {
            payload.putIfAbsent("agent", agent);
        }
        if (roleType != null) {
            payload.putIfAbsent("role_type", roleType);
        }
        payload.putIfAbsent("timestamp", nowIso);
        Path p = resultPath(taskId, stepId);
        JsonFiles.write(p, payload);
        return p;
    }

    /** acceptance.json 落盘（msg-results/{taskId}/acceptance.json，python _write_acceptance 对等）。 */
    public Path writeAcceptance(String taskId, Map<String, Object> payload) {
        Path p = dataDir.resolve("msg-results").resolve(taskId).resolve("acceptance.json");
        JsonFiles.write(p, payload);
        return p;
    }

    /** 读步骤结果：result_ref 优先（相对 store 的 msg-results 前缀），回退标准路径。 */
    public Map<String, Object> readStepResult(String taskId, Map<String, Object> step) {
        for (Path p : pathsToTry(taskId, step)) {
            Map<String, Object> data = JsonFiles.readMap(p);
            if (data != null) {
                return data;
            }
        }
        return null;
    }

    private List<Path> pathsToTry(String taskId, Map<String, Object> step) {
        List<Path> paths = new ArrayList<>();
        String ref = str(step.get("result_ref"));
        String sid = str(step.get("step_id"));
        if (!ref.isEmpty()) {
            if (ref.startsWith("msg-results/")) {
                paths.add(dataDir.resolve(ref));
            }
        }
        if (!sid.isEmpty()) {
            paths.add(resultPath(taskId, sid));
        }
        return paths;
    }

    /**
     * 校验结果是否对应当前步骤。返回 null = 通过；否则返回拒绝原因
     * （与 python 拒绝码一致：wrong_task/untrusted_source/wrong_step_id/
     * stale_prior_step/wrong_step/wrong_agent/inconclusive）。
     */
    public String resultAppliesToStep(Map<String, Object> result, String taskId,
                                      Map<String, Object> step, List<Map<String, Object>> chain) {
        String rid = firstNonEmpty(result.get("task_id"), result.get("task"));
        if (!rid.isEmpty() && !rid.equals(taskId)) {
            return "wrong_task";
        }
        String src = str(result.get("source")).toLowerCase();
        if (src.contains("auto-linked-from") || src.contains("auto-recovered-from")) {
            return "untrusted_source";
        }
        int stepNum = intOr(step.get("step"), chain.indexOf(step) + 1);
        String sid = str(step.get("step_id"));
        String resultSid = str(result.get("step_id"));
        if (!resultSid.isEmpty() && !sid.isEmpty() && !resultSid.equals(sid)) {
            return "wrong_step_id";
        }
        Object rstep = result.get("pipeline_step");
        if (rstep != null) {
            int rs = intOr(rstep, -1);
            if (rs < stepNum) {
                return "stale_prior_step";
            }
            if (rs != stepNum) {
                return "wrong_step";
            }
        }
        String agent = firstNonEmpty(result.get("agent"), result.get("from"));
        String expected = firstNonEmpty(step.get("to_agent"), step.get("to_person"));
        if (!agent.isEmpty() && !expected.isEmpty() && !agent.equals(expected)) {
            return "wrong_agent";
        }
        String c = str(result.get("conclusion")).toLowerCase();
        String status = str(result.get("status")).toLowerCase();
        // status=done|completed 同为终态口径（G10：msg-results 契约回执常只有 status）
        if (!DONE_CONCLUSIONS.contains(c) && !"completed".equals(status) && !"done".equals(status)) {
            return "inconclusive";
        }
        return null;
    }

    private static String firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return String.valueOf(v);
            }
        }
        return "";
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
}
