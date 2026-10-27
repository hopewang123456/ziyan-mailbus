package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.task.StepFsmState;
import io.github.hopewang123456.mailbus.domain.task.TaskFsmState;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.time.Clock;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 结果消化引擎 — python {@code pipeline/trigger.trigger_task} +
 * {@code task_fsm.apply_submit} 的简化对等（M2b）：
 * 读 msg-results → 校验 → verify → 完成当前步 → 推进（planned 消费 /
 * role-flow SoT / next_role_type 显式指定）→ 派发下一步；链尾进入
 * accepting（S+验收员自动终验）。
 *
 * <p>偏差（M2c+）：verify auto-retry 通道、_resume_planned_advance、
 * collab 并行组、audit 同步、delivery normalizer、token 台账入账。
 */
public class ResultIngestService {

    private final Path dataDir;
    private final TaskRepository tasks;
    private final RoleResolverService resolver;
    private final HumanQueueService humanQueue;
    private final StepDispatcher dispatcher;
    private final TaskFsmViews fsm;
    private final StepResultIo io;
    private final ResultVerifier verifier;
    private final RoleFlowService roleFlow;

    public ResultIngestService(Path dataDir, Clock clock, TaskRepository tasks,
                               RoleResolverService resolver, HumanQueueService humanQueue) {
        this.dataDir = dataDir;
        this.tasks = tasks;
        this.resolver = resolver;
        this.humanQueue = humanQueue;
        this.dispatcher = new StepDispatcher(dataDir, clock);
        this.fsm = new TaskFsmViews(clock);
        this.io = new StepResultIo(dataDir);
        this.verifier = new ResultVerifier(dataDir);
        this.roleFlow = new RoleFlowService(dataDir);
    }

    /** 扫描全部 executing 任务（scheduler 兜底入口）。返回推进摘要。 */
    public Map<String, Object> scanAll() {
        int advanced = 0;
        List<String> touched = new ArrayList<>();
        for (Map<String, Object> task : tasks.listAll()) {
            String state = str(orMap(task.get("fsm")).get("state"));
            if (!TaskFsmState.EXECUTING.value().equals(state)) {
                continue;
            }
            String id = str(task.get("task_id"));
            Map<String, Object> out = ingestTask(id);
            String action = str(out.get("action"));
            if (!action.isEmpty() && !"skipped".equals(str(out.get("kind")))) {
                advanced++;
                touched.add(id + ":" + action);
            }
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("scanned", true);
        out.put("advanced", advanced);
        out.put("actions", touched);
        return out;
    }

    /**
     * agent 回执提交（POST /api/agents/{agent}/step-result）— 校验、写
     * msg-results 落盘、立即推进（G-02 对等）。返回 {status, body}。
     */
    public Map<String, Object> submitStepResult(String agent, Map<String, Object> body) {
        String taskId = str(body.get("task_id")).trim();
        String stepId = str(body.get("step_id")).trim();
        String conclusion = str(body.getOrDefault("conclusion", "done")).trim().toLowerCase();
        if (conclusion.isEmpty()) {
            conclusion = "done";
        }
        if (taskId.isEmpty() || stepId.isEmpty()) {
            return resp(400, "missing_fields", "task_id 和 step_id 必填");
        }
        if (!StepResultIo.DONE_CONCLUSIONS.contains(conclusion)) {
            return resp(400, "invalid_conclusion", "conclusion 可选值: " + String.join(", ", StepResultIo.DONE_CONCLUSIONS));
        }
        for (String part : List.of(taskId, stepId)) {
            boolean safe = !part.startsWith(".") && part.chars()
                    .allMatch(c -> Character.isLetterOrDigit(c) || c == '-' || c == '_' || c == '.');
            if (!safe) {
                return resp(400, "invalid_id", "task_id/step_id 含非法字符");
            }
        }

        boolean positive = conclusion.equals("done") || conclusion.equals("pass")
                || conclusion.equals("approved");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", positive ? "completed" : "error");
        result.put("conclusion", conclusion);
        String summary = firstNonEmpty(body.get("summary"), body.get("text"));
        result.put("summary", summary);
        result.put("agent", agent);
        if (body.get("artifacts") instanceof List<?> arts && !arts.isEmpty()) {
            result.put("artifacts", arts.stream().limit(20).map(String::valueOf).toList());
        }
        Path path = io.writeStepResult(taskId, stepId, result, agent, null, fsm.nowIso());

        Map<String, Object> ingestOut = ingestTask(taskId);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("result_path", path.toString());
        out.put("ingest", ingestOut);
        out.put("note", "结果已落盘并推进；调度器 scan 兜底");
        return Map.of("status", 200, "body", out);
    }

    private static Map<String, Object> resp(int status, String error, String message) {
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("status", "error");
        b.put("error", error);
        b.put("message", message);
        return Map.of("status", status, "body", b);
    }

    /** 单任务推进（python trigger_task 对等返回形状）。 */
    public Map<String, Object> ingestTask(String taskId) {
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            return Map.of("ok", false, "error", "not_found");
        }
        Map<String, Object> task = found.get();
        fsm.ensureFsm(task, 50);
        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        String state = str(fsmDoc.get("state"));
        if (TaskFsmState.PAUSED.value().equals(state) || TaskFsmState.CANCELLED.value().equals(state)) {
            return Map.of("ok", true, "kind", "skipped", "skipped", "paused_or_cancelled");
        }
        if (!TaskFsmState.EXECUTING.value().equals(state) && !TaskFsmState.CREATED.value().equals(state)) {
            return Map.of("ok", true, "kind", "skipped", "skipped", "not_executable");
        }

        List<Map<String, Object>> chain = rawChain(task);
        Map<String, Object> current = fsm.activeStep(task);
        if (current == null) {
            return Map.of("ok", true, "kind", "skipped", "skipped", "no_active_step");
        }

        // 已完成态修复：全链完成且 planned 清空 → 补进 accepting（python 同兜底）
        if (fsm.isTerminalStep(current)) {
            boolean allDone = chain.stream().allMatch(fsm::isTerminalStep);
            if (allDone && plannedRemaining(chain).isEmpty() && !"success".equals(str(task.get("status")))) {
                String outcome = enterAcceptingOrSucceed(task, Map.of());
                tasks.save(taskId, task);
                return Map.of("ok", true, "kind", "skipped", "action", outcome, "skipped", "step_completed");
            }
            return Map.of("ok", true, "kind", "skipped", "skipped", "step_completed");
        }

        if (Boolean.TRUE.equals(current.get("result_consumed"))) {
            return Map.of("ok", true, "kind", "skipped", "skipped", "result_consumed");
        }

        Map<String, Object> result = io.readStepResult(taskId, current);
        if (result == null) {
            return Map.of("ok", true, "kind", "skipped", "skipped", "no_result");
        }
        String reject = io.resultAppliesToStep(result, taskId, current, chain);
        if (reject != null) {
            return Map.of("ok", true, "kind", "skipped", "skipped", reject);
        }
        return applySubmit(taskId, task, result);
    }

    /** python apply_submit 简化对等。 */
    public Map<String, Object> applySubmit(String taskId, Map<String, Object> task,
                                           Map<String, Object> result) {
        fsm.ensureFsm(task, 50);
        List<Map<String, Object>> chain = rawChain(task);
        Map<String, Object> step = resolveStepForAgent(task, str(result.get("agent")));
        if (step == null) {
            return Map.of("ok", false, "error", "no_active_step");
        }
        String reject = io.resultAppliesToStep(result, taskId, step, chain);
        if (reject != null) {
            return Map.of("ok", false, "error", reject);
        }

        String conclusion = str(result.getOrDefault("conclusion", "done")).toLowerCase();
        Integer roleType = step.get("role_type") == null ? null : intOr(step.get("role_type"), 0);

        // verify（M2b 简化：失败直接 blocked，auto-retry 通道偏差不做）
        String vErr = verifier.verifyStepResult(roleType, conclusion, result);
        if (vErr != null) {
            fsm.asMap(task.get("fsm")).put("state", TaskFsmState.BLOCKED.value());
            fsm.appendHistory(task, "verify_blocked", Map.of("error", vErr));
            tasks.save(taskId, task);
            return Map.of("ok", true, "action", "blocked", "reason", vErr);
        }

        // 完成当前步
        step.put("fsm_state", StepFsmState.COMPLETED.value());
        step.put("status", "completed");
        step.put("completed_at", fsm.nowIso());
        step.put("result_consumed", true);
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("conclusion", conclusion);
        report.put("summary", str(result.get("summary")));
        report.put("template", "report");
        report.put("details", result);
        step.put("report", report);
        task.put("updated_at", fsm.nowIso());
        fsm.appendHistory(task, "submit", Map.of(
                "step_id", str(step.get("step_id")),
                "agent", str(step.get("to_agent")),
                "conclusion", conclusion));

        // ── 下一步解析 ──
        Integer nextRoleType = intOrNull(result.get("next_role_type"));
        if (nextRoleType == null) {
            List<Integer> planned = plannedRemaining(chain);
            if (!planned.isEmpty()) {
                Map<String, Object> head = chain.get(0);
                nextRoleType = planned.get(0);
                head.put("planned_role_types", planned.subList(1, planned.size()));
            }
        }
        if (nextRoleType == null && roleType != null && roleFlow.isTerminal(roleType, conclusion)) {
            String outcome = enterAcceptingOrSucceed(task, result);
            tasks.save(taskId, task);
            return Map.of("ok", true, "action", outcome);
        }
        if (nextRoleType == null && roleType != null) {
            nextRoleType = roleFlow.nextRoleType(roleType, conclusion);
        }
        if (nextRoleType == null && StepResultIo.BLOCKING_CONCLUSIONS.contains(conclusion)) {
            Integer fallback = roleFlow.blockedFallbackRoleType();
            if (fallback != null) {
                nextRoleType = fallback; // rollback_flow 简化：回退岗直接推进
            }
        }
        if (nextRoleType == null) {
            fsm.asMap(task.get("fsm")).put("state", TaskFsmState.BLOCKED.value());
            fsm.appendHistory(task, "blocked", Map.of(
                    "conclusion", conclusion, "step_id", str(step.get("step_id"))));
            tasks.save(taskId, task);
            return Map.of("ok", true, "action", "blocked", "reason", "no_next_assignee");
        }

        String assignee = pickAssignee(chain, nextRoleType);
        if (assignee == null || assignee.isEmpty()) {
            fsm.asMap(task.get("fsm")).put("state", TaskFsmState.BLOCKED.value());
            tasks.save(taskId, task);
            return Map.of("ok", false, "error", "no_assignee", "action", "blocked");
        }

        // 创建并派发下一步
        Map<String, Object> nxt = createNextStep(task, nextRoleType, assignee,
                str(step.get("to_agent")));
        chain.add(nxt);
        task.put("assignee", assignee);
        fsm.asMap(task.get("fsm")).put("state", TaskFsmState.EXECUTING.value());
        fsm.asMap(task.get("fsm")).put("active_step_id", nxt.get("step_id"));
        task.put("status", "running");
        fsm.appendHistory(task, "advance", Map.of(
                "from_step", str(step.get("step_id")),
                "to_step", str(nxt.get("step_id")),
                "to_person", assignee,
                "kind", "advance"));
        tasks.save(taskId, task);

        boolean dispatchOk = dispatcher.dispatchStep(task, nxt, str(result.get("summary")));
        if (dispatchOk) {
            tasks.save(taskId, task);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", true);
        out.put("action", "advance");
        out.put("next_step_id", nxt.get("step_id"));
        out.put("next_person", assignee);
        out.put("next_role_type", nextRoleType);
        out.put("dispatch_ok", dispatchOk);
        return out;
    }

    /** python enter_accepting_or_succeed：S+role_type 12+approved 自动终验。 */
    private String enterAcceptingOrSucceed(Map<String, Object> task, Map<String, Object> result) {
        fsm.ensureFsm(task, 50);
        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        String tier = str(task.getOrDefault("tier", "M")).toUpperCase();
        String conclusion = str(result.getOrDefault("conclusion", "")).toLowerCase();
        List<Map<String, Object>> chain = TaskFsmViews.chain(task);
        Integer lastRt = chain.isEmpty() || chain.get(chain.size() - 1).get("role_type") == null
                ? null : intOr(chain.get(chain.size() - 1).get("role_type"), 0);

        String taskId = str(task.get("task_id"));
        if ("S".equals(tier) && lastRt != null && lastRt == 12 && "approved".equals(conclusion)) {
            writeAcceptance(taskId, "approved",
                    str(result.getOrDefault("agent", chain.isEmpty() ? "" : str(chain.get(chain.size() - 1).get("to_agent")))),
                    "auto", "S-tier auto acceptance (role_type=12, approved)", "");
            fsmDoc.put("state", TaskFsmState.SUCCEEDED.value());
            task.put("status", "success");
            fsmDoc.remove("substate");
            fsmDoc.remove("human_queue_id");
            fsm.appendHistory(task, "auto_accept", Map.of("method", "auto"));
            return "terminal";
        }

        fsmDoc.put("state", TaskFsmState.ACCEPTING.value());
        fsmDoc.remove("substate");
        task.put("status", "pending");
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("type", "final_acceptance");
        item.put("status", "pending");
        item.put("title", "终验任务 · " + taskId.substring(0, Math.min(32, taskId.length())));
        item.put("task_id", taskId);
        String hid = humanQueue.enqueue(item);
        fsmDoc.put("human_queue_id", hid);
        fsm.appendHistory(task, "accepting", Map.of("human_queue_id", hid));
        return "accepting";
    }

    /** acceptance.json 落盘（msg-results/{tid}/acceptance.json，python 对等）。 */
    public void writeAcceptance(String taskId, String decision, String reviewer,
                                String method, String comment, String reason) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_id", taskId);
        payload.put("decision", decision);
        payload.put("reviewer", reviewer);
        payload.put("method", method);
        payload.put("comment", comment);
        payload.put("reason", reason);
        payload.put("attachments", List.of());
        payload.put("timestamp", fsm.nowIso());
        io.writeAcceptance(taskId, payload);
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> rawChain(Map<String, Object> task) {
        Object chainObj = task.get("chain");
        if (chainObj instanceof List<?> rawList) {
            return (List<Map<String, Object>>) (List<?>) rawList;
        }
        List<Map<String, Object>> chain = new ArrayList<>();
        task.put("chain", chain);
        return chain;
    }

    private static List<Integer> plannedRemaining(List<Map<String, Object>> chain) {
        if (chain.isEmpty()) {
            return List.of();
        }
        Object planned = chain.get(0).get("planned_role_types");
        List<Integer> out = new ArrayList<>();
        if (planned instanceof List<?> list) {
            for (Object o : list) {
                out.add(intOr(o, 0));
            }
        }
        return out;
    }

    /** 下一步 assignee：首步 pin 在候选内沿用；否则候选池排除已服务者取首个（python _resolve_role_type_assignee）。 */
    private String pickAssignee(List<Map<String, Object>> chain, int roleType) {
        List<String> candidates = resolver.roleCandidates(roleType);
        if (candidates.isEmpty()) {
            return "";
        }
        String pin = chain.isEmpty() ? null : str(chain.get(0).get("pin_agent"));
        if (pin != null && !pin.isEmpty() && candidates.contains(pin)) {
            return pin;
        }
        Set<String> served = new HashSet<>();
        for (Map<String, Object> s : chain) {
            String p = str(s.get("to_person"));
            if (!p.isEmpty()) {
                served.add(p);
            }
        }
        for (String c : candidates) {
            if (!served.contains(c)) {
                return c;
            }
        }
        return candidates.get(0);
    }

    private Map<String, Object> createNextStep(Map<String, Object> task, int roleType,
                                               String assignee, String fromPerson) {
        List<Map<String, Object>> chain = TaskFsmViews.chain(task);
        int sn = chain.size() + 1;
        String stepId = "s" + sn;
        String taskId = str(task.get("task_id"));
        Map<String, Object> step = new LinkedHashMap<>();
        step.put("step", sn);
        step.put("step_id", stepId);
        step.put("attempt", 1);
        step.put("role_type", roleType);
        step.put("from_person", fromPerson);
        step.put("to_agent", assignee);
        step.put("to_person", assignee);
        step.put("status", "running");
        step.put("fsm_state", StepFsmState.QUEUED.value());
        step.put("started_at", fsm.nowIso());
        step.put("completed_at", null);
        step.put("report", null);
        step.put("result_consumed", false);
        step.put("task_id", taskId);
        step.put("result_ref", "msg-results/" + taskId + "/step-" + stepId + ".json");
        return step;
    }

    /** python resolve_step_for_agent：agent 的非终态步优先，active 兜底。 */
    private Map<String, Object> resolveStepForAgent(Map<String, Object> task, String agent) {
        if (agent != null && !agent.isEmpty()) {
            for (Map<String, Object> step : TaskFsmViews.chain(task)) {
                String who = firstNonEmpty(step.get("to_agent"), step.get("to_person"));
                if (agent.equals(who) && !fsm.isTerminalStep(step)) {
                    return step;
                }
            }
        }
        return fsm.activeStep(task);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> orMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
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

    private static Integer intOrNull(Object o) {
        if (o == null) {
            return null;
        }
        try {
            return (int) Double.parseDouble(String.valueOf(o));
        } catch (RuntimeException e) {
            return null;
        }
    }

    private static int intOr(Object o, int fallback) {
        Integer v = intOrNull(o);
        return v == null ? fallback : v;
    }
}
