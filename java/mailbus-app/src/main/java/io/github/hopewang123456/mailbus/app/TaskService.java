package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.task.StepFsmState;
import io.github.hopewang123456.mailbus.domain.task.TaskFsmState;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 任务引擎 — python {@code api/handlers_tasks.py create_task_from_envelope} +
 * {@code task_fsm.py} 动作集的 java 对等（M2a：explicit 路径 + 七 FSM 动作 +
 * 首步派发；任务文件与 python 双栈共享，见 M2-S1）。
 *
 * <p>偏差清单（M2b+ 回收）：auto 计划 / collab 并行组 / transport_router /
 * task lock / bind_workflow / requires_audit 推断 / denied-replan。
 */
public class TaskService {

    private final Path dataDir;
    private final TaskRepository tasks;
    private final RoleResolverService resolver;
    private final HumanQueueService humanQueue;
    private final StepDispatcher dispatcher;
    private final EnvelopeValidator validator;
    private final TaskFsmViews fsm;
    private TaskPlannerService planner; // M2c auto 模式（boot 注入；null = 未配置走 400）

    public TaskService(Path dataDir, Clock clock, TaskRepository tasks,
                       RoleResolverService resolver, HumanQueueService humanQueue) {
        this.dataDir = dataDir;
        this.tasks = tasks;
        this.resolver = resolver;
        this.humanQueue = humanQueue;
        this.dispatcher = new StepDispatcher(dataDir, clock);
        this.validator = new EnvelopeValidator();
        this.fsm = new TaskFsmViews(clock);
    }

    /** M2c：注入 planner（tier0 规则 + 可选 LLM），解锁 auto 模式。 */
    public void setPlanner(TaskPlannerService planner) {
        this.planner = planner;
    }

    /** (httpStatus, body) 对——python handler 的 (resp, status) 元组。 */
    public record Result(int status, Map<String, Object> body) {
        static Result of(int status, String error, String message) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", error);
            if (message != null) {
                b.put("message", message);
            }
            return new Result(status, b);
        }
    }

    // ── POST /api/tasks/create ──────────────────────────────────────────────

    public Result createFromEnvelope(Map<String, Object> body) {
        if (validator.isLegacyCreateBody(body)) {
            return Result.of(410, "legacy_deprecated",
                    "Use A2A Envelope; see store/rules/a2a-task-create-api.md");
        }
        if (body != null && "auto".equals(str(body.get("mode")))) {
            // M2c：tier0 规则 → LLM（与 draft 同一 planner，所见即所发）
            if (planner == null) {
                return Result.of(400, "auto_plan_unsupported",
                        "planner not wired (unit context); use explicit planned_chain");
            }
        }
        List<String> errors = validator.validate(body);
        if (!errors.isEmpty()) {
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "error");
            b.put("error", "schema_invalid");
            b.put("details", errors);
            return new Result(400, b);
        }
        String taskId = str(body.get("task_id"));
        if (tasks.find(taskId).isPresent()) {
            return Result.of(409, "task_exists", "任务 " + taskId + " 已存在");
        }

        List<Map<String, Object>> plannedChain;
        Map<String, Object> planMeta;
        if (body != null && "auto".equals(str(body.get("mode")))) {
            Map<String, Object> planned;
            try {
                planned = planner.plan(body);
            } catch (TaskPlannerService.LlmError e) {
                return Result.of(503, "llm_error", String.valueOf(e.getMessage()));
            } catch (TaskPlannerService.PlanError e) {
                Map<String, Object> b = new LinkedHashMap<>();
                b.put("status", "error");
                b.put("error", e.code);
                b.put("message", String.valueOf(e.getMessage()));
                return new Result(400, b);
            }
            plannedChain = plannedChain(planned);
            planMeta = planned.get("plan_meta") instanceof Map<?, ?> m ? new LinkedHashMap<>(orMap(m)) : new LinkedHashMap<>();
        } else {
            plannedChain = plannedChain(body);
            planMeta = Map.of();
        }

        Map<String, Object> task = buildTask(taskId, body, plannedChain, planMeta);
        tasks.save(taskId, task);

        if (needsPlanApproval(body)) {
            fsm.asMap(task.get("fsm")).put("state", TaskFsmState.CREATED.value());
            fsm.asMap(task.get("fsm")).put("substate", "await_plan_approval");
            task.put("status", "pending");
            List<Map<String, Object>> chain = TaskFsmViews.chain(task);
            List<Integer> planned = chain.isEmpty() ? List.of()
                    : intList(chain.get(0).get("planned_role_types"));
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("type", "plan_approval");
            item.put("status", "pending");
            item.put("title", "批准任务计划 · " + taskId.substring(0, Math.min(32, taskId.length())));
            item.put("hint", "planned_role_types: " + planned);
            item.put("task_id", taskId);
            Map<String, Object> context = new LinkedHashMap<>();
            context.put("intent", str(task.get("intent")));
            context.put("tier", task.get("tier"));
            context.put("task_type", task.get("task_type"));
            context.put("planned_role_types", planned);
            context.put("plan_meta", task.get("plan_meta"));
            item.put("context", context);
            String hid = humanQueue.enqueue(item);
            fsm.asMap(task.get("fsm")).put("human_queue_id", hid);
            tasks.save(taskId, task);
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("status", "ok");
            b.put("task", task);
            b.put("human_queue_id", hid);
            return new Result(201, b);
        }

        startExecuting(task);
        tasks.save(taskId, task);
        dispatcher.dispatchFirstStep(task);
        tasks.save(taskId, task);
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("status", "ok");
        b.put("task", task);
        return new Result(201, b);
    }

    /** v3 envelope → 任务字典（python tracker.create_from_envelope + init_chain_from_planned 简单路径）。 */
    private Map<String, Object> buildTask(String taskId, Map<String, Object> envelope,
                                          List<Map<String, Object>> planned,
                                          Map<String, Object> planMetaIn) {
        Map<String, Object> first = planned.get(0);
        int rt0 = intOr(first.get("role_type"), 0);
        String pin0 = str(first.get("pin_agent"));
        RoleResolverService.Resolved resolved = resolver.resolve(rt0, pin0);
        List<Integer> rest = planned.subList(1, planned.size()).stream()
                .map(p -> intOr(p.get("role_type"), 0)).toList();

        Map<String, Object> step = new LinkedHashMap<>();
        step.put("step", 1);
        step.put("step_id", "s1");
        step.put("role_type", rt0);
        step.put("to_agent", resolved.agent());
        step.put("to_person", resolved.agent());
        step.put("planned_role_types", rest);
        step.put("dispatch_meta", resolved.meta());
        step.put("status", "running");
        step.put("fsm_state", StepFsmState.QUEUED.value());
        step.put("started_at", fsm.nowIso());
        step.put("completed_at", null);
        step.put("report", null);
        step.put("result_consumed", false);
        step.put("task_id", taskId);
        step.put("result_ref", "msg-results/" + taskId + "/step-s1.json");
        if (!pin0.isEmpty()) {
            step.put("pin_agent", pin0);
        }

        String intent = str(envelope.get("intent"));
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("task_id", taskId);
        task.put("protocol_version", str(envelope.getOrDefault("protocol_version", "mailbus-a2a/1")));
        task.put("intent", intent);
        task.put("summary", intent.length() > 120 ? intent.substring(0, 120) : intent);
        task.put("initiator", str(envelope.getOrDefault("initiator", "human")));
        task.put("mode", envelope.get("mode"));
        task.put("tier", envelope.get("tier"));
        task.put("task_type", envelope.get("task_type"));
        task.put("assignee", resolved.agent());
        task.put("status", "pending");
        task.put("chain", new ArrayList<>(List.of(step)));
        task.put("extensions", orNewMap(envelope.get("extensions")));
        task.put("constraints", orNewMap(envelope.get("constraints")));
        task.put("acceptance", orNewMap(envelope.get("acceptance")));
        task.put("artifacts_in", envelope.get("artifacts_in") instanceof List<?> l ? l : List.of());
        Map<String, Object> planMeta = new LinkedHashMap<>();
        if (!planMetaIn.isEmpty()) {
            planMeta.putAll(planMetaIn);
        } else {
            planMeta.put("method", "rules");
            planMeta.put("task_type_guess", envelope.get("task_type"));
            planMeta.put("confidence", 1.0);
            planMeta.put("provider_used", "rules");
        }
        task.put("plan_meta", planMeta);
        task.put("requires_audit", false);
        task.put("error", null);
        task.put("reminded_count", 0);
        task.put("created_at", fsm.nowIso());
        task.put("updated_at", fsm.nowIso());
        Map<String, Object> fsmDoc = new LinkedHashMap<>();
        fsmDoc.put("state", TaskFsmState.CREATED.value());
        fsmDoc.put("version", 1);
        fsmDoc.put("priority", intOr(orMap(envelope.get("fsm")).get("priority"), 50));
        fsmDoc.put("history", new ArrayList<>());
        fsmDoc.put("active_step_id", "s1");
        task.put("fsm", fsmDoc);
        return task;
    }

    private void startExecuting(Map<String, Object> task) {
        fsm.ensureFsm(task, 50);
        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        fsmDoc.put("state", TaskFsmState.EXECUTING.value());
        fsmDoc.remove("substate");
        fsmDoc.remove("gate_id");
        task.put("status", "running");
    }

    /** python needs_plan_approval 对等（M2a 只读 mailbus_internal_llm.guardrails）。 */
    private boolean needsPlanApproval(Map<String, Object> envelope) {
        if (Boolean.TRUE.equals(envelope.get("await_plan_approval"))) {
            return true;
        }
        Map<String, Object> config = orMap(JsonFiles.readMap(dataDir.resolve("config.json")));
        Map<String, Object> llmCfg = orMap(config.get("mailbus_internal_llm"));
        Map<String, Object> guardrails = orMap(llmCfg.get("guardrails"));
        String tierMin = str(guardrails.getOrDefault("await_plan_approval_tier_min", "M"));
        String tier = str(envelope.get("tier"));
        if (tier.isEmpty()) {
            tier = "S";
        }
        return tierOrder(tier) >= tierOrder(tierMin);
    }

    private static int tierOrder(String tier) {
        return switch (tier) {
            case "S" -> 0;
            case "M" -> 1;
            case "L" -> 2;
            default -> 1;
        };
    }

    // ── GET /api/tasks · /api/tasks/{id} · /fsm ────────────────────────────

    public Map<String, Object> listTasks(String status, String assignee, int limit, int offset) {
        List<Map<String, Object>> all = new ArrayList<>();
        for (Map<String, Object> t : tasks.listAll()) {
            String id = str(t.get("task_id"));
            if (id.startsWith("remind-") || id.startsWith("tracker-remind-")) {
                continue; // exclude_noise 默认开（python 语义）
            }
            if (status != null && !status.isEmpty() && !status.equals(str(t.get("status")))) {
                continue;
            }
            if (assignee != null && !assignee.isEmpty() && !assignee.equals(str(t.get("assignee")))) {
                continue;
            }
            all.add(t);
        }
        int total = all.size();
        int from = Math.min(offset, total);
        int to = Math.min(from + Math.max(1, limit), total);
        List<Map<String, Object>> page = all.subList(from, to);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("tasks", page);
        out.put("count", page.size());
        out.put("total", total);
        out.put("limit", limit);
        out.put("offset", offset);
        out.put("exclude_noise", true);
        return out;
    }

    public Optional<Map<String, Object>> getTask(String taskId) {
        return tasks.find(taskId);
    }

    public Optional<Map<String, Object>> fsmSummary(String taskId) {
        return tasks.find(taskId).map(fsm::fsmSummary);
    }

    // ── POST /api/tasks/{id}/fsm/{action} ──────────────────────────────────

    public Result fsmAction(String taskId, String action, Map<String, Object> body) {
        Optional<Map<String, Object>> found = tasks.find(taskId);
        if (found.isEmpty()) {
            return Result.of(404, "not_found", null);
        }
        Map<String, Object> task = found.get();
        Map<String, Object> b = body == null ? Map.of() : body;
        String reason = str(b.get("reason"));

        switch (action) {
            case "approve-plan" -> {
                return approvePlan(taskId, task, b, reason);
            }
            case "rollback" -> {
                return rollback(taskId, task, b, reason);
            }
            case "skip" -> {
                Map<String, Object> step = fsm.activeStep(task);
                if (step == null) {
                    return Result.of(400, "no_active_step", null);
                }
                step.put("fsm_state", StepFsmState.SKIPPED.value());
                step.put("status", "skipped");
                step.put("completed_at", fsm.nowIso());
                step.put("skip_reason", reason);
                fsm.appendHistory(task, "skip", Map.of("step_id", str(step.get("step_id")), "reason", reason));
                tasks.save(taskId, task);
                return ok(task, "skip", Map.of("needs_manual_advance", true));
            }
            case "cancel" -> {
                Map<String, Object> step = fsm.activeStep(task);
                if (step != null) {
                    step.put("fsm_state", StepFsmState.SUPERSEDED.value());
                }
                fsm.asMap(task.get("fsm")).put("state", TaskFsmState.CANCELLED.value());
                task.put("status", "cancelled");
                task.put("error", reason.isEmpty() ? "cancelled" : reason);
                fsm.appendHistory(task, "cancel", Map.of("reason", reason));
                tasks.save(taskId, task);
                return ok(task, "cancel", null);
            }
            case "pause" -> {
                fsm.ensureFsm(task, 50);
                fsm.asMap(task.get("fsm")).put("state", TaskFsmState.PAUSED.value());
                task.put("status", "paused");
                task.put("pause_reason", reason);
                fsm.appendHistory(task, "pause", Map.of("reason", reason));
                tasks.save(taskId, task);
                return ok(task, "pause", null);
            }
            case "resume" -> {
                fsm.ensureFsm(task, 50);
                if (!TaskFsmState.PAUSED.value().equals(str(fsm.asMap(task.get("fsm")).get("state")))) {
                    return ok(task, "noop", null);
                }
                fsm.asMap(task.get("fsm")).put("state", TaskFsmState.EXECUTING.value());
                task.put("status", "running");
                task.remove("pause_reason");
                fsm.appendHistory(task, "resume", null);
                tasks.save(taskId, task);
                return ok(task, "resume", null);
            }
            case "priority" -> {
                fsm.ensureFsm(task, 50);
                Object p = b.get("priority");
                if (p == null) {
                    Map<String, Object> err = new LinkedHashMap<>();
                    err.put("error", "missing priority");
                    return new Result(400, err);
                }
                fsm.asMap(task.get("fsm")).put("priority", intOr(p, 50));
                tasks.save(taskId, task);
                return ok(task, "priority", null);
            }
            case "accept" -> {
                return accept(taskId, task, b, reason);
            }
            case "approve-join", "continue" -> {
                return Result.of(501, "not_implemented",
                        "java action '" + action + "' lands with M2c+ (collab/resume paths)");
            }
            default -> {
                Map<String, Object> err = new LinkedHashMap<>();
                err.put("error", "unknown action: " + action);
                return new Result(400, err);
            }
        }
    }

    private Result approvePlan(String taskId, Map<String, Object> task,
                               Map<String, Object> body, String reason) {
        fsm.ensureFsm(task, 50);
        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        if (!TaskFsmState.CREATED.value().equals(str(fsmDoc.get("state")))
                || !"await_plan_approval".equals(str(fsmDoc.get("substate")))) {
            return Result.of(400, "invalid_fsm_state", null);
        }
        String decision = str(body.getOrDefault("decision", "")).toLowerCase();
        String reviewer = str(body.getOrDefault("reviewer", "human"));
        Map<String, Object> resolution = new LinkedHashMap<>();
        resolution.put("decision", decision);
        resolution.put("reviewer", reviewer);
        resolution.put("comment", str(body.get("comment")));
        resolution.put("reason", reason);

        if ("approved".equals(decision)) {
            fsmDoc.remove("substate");
            startExecuting(task);
            boolean dispatchOk = dispatcher.dispatchFirstStep(task);
            humanQueue.closeByTask(taskId, "plan_approval", resolution);
            fsmDoc.remove("human_queue_id");
            fsm.appendHistory(task, "approve_plan",
                    Map.of("reviewer", reviewer, "dispatch_ok", dispatchOk));
            tasks.save(taskId, task);
            Map<String, Object> out = okBody(task, "approve_plan", null);
            out.put("dispatch_ok", dispatchOk);
            return new Result(200, out);
        }
        if ("denied".equals(decision)) {
            if (reason.isEmpty()) {
                return Result.of(400, "missing_reason", null);
            }
            // M2a 简化：denied → 取消任务（python 的 replan 重规划属 M2c）
            humanQueue.closeByTask(taskId, "plan_approval", resolution);
            fsmDoc.put("state", TaskFsmState.CANCELLED.value());
            task.put("status", "cancelled");
            task.put("error", "plan_denied: " + reason);
            fsm.appendHistory(task, "deny_plan", Map.of("reviewer", reviewer, "reason", reason));
            tasks.save(taskId, task);
            Map<String, Object> out = okBody(task, "deny_plan", null);
            out.put("dispatch_ok", false);
            return new Result(200, out);
        }
        return Result.of(400, "invalid_decision", "decision must be approved or denied");
    }

    /** accept 动作（M2b）— python apply_accept 对等：accepting 终验。 */
    private Result accept(String taskId, Map<String, Object> task,
                          Map<String, Object> body, String reason) {
        fsm.ensureFsm(task, 50);
        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        if (!TaskFsmState.ACCEPTING.value().equals(str(fsmDoc.get("state")))) {
            return Result.of(400, "invalid_fsm_state", null);
        }
        String decision = str(body.getOrDefault("decision", "")).toLowerCase();
        String reviewer = str(body.getOrDefault("reviewer", "human"));
        java.util.List<?> attachments = body.get("attachments") instanceof java.util.List<?> l ? l : java.util.List.of();

        if ("approved".equals(decision)) {
            new StepResultIo(dataDir).writeAcceptance(taskId, new java.util.LinkedHashMap<>(Map.of(
                    "task_id", taskId, "decision", "approved", "reviewer", reviewer,
                    "method", "manual", "comment", str(body.get("comment")),
                    "reason", reason, "attachments", attachments,
                    "timestamp", fsm.nowIso())));
            fsmDoc.put("state", TaskFsmState.SUCCEEDED.value());
            task.put("status", "success");
            humanQueue.closeByTask(taskId, "final_acceptance", new java.util.LinkedHashMap<>(Map.of(
                    "decision", "approved", "reviewer", reviewer,
                    "comment", str(body.get("comment")), "attachments", attachments)));
            fsmDoc.remove("human_queue_id");
            fsm.appendHistory(task, "accept", Map.of("reviewer", reviewer));
            tasks.save(taskId, task);
            Map<String, Object> out = okBody(task, "accept", null);
            out.put("dispatch_ok", null);
            return new Result(200, out);
        }
        if ("denied".equals(decision)) {
            if (reason.isEmpty()) {
                return Result.of(400, "missing_reason", null);
            }
            new StepResultIo(dataDir).writeAcceptance(taskId, new java.util.LinkedHashMap<>(Map.of(
                    "task_id", taskId, "decision", "denied", "reviewer", reviewer,
                    "method", "manual", "reason", reason, "attachments", attachments,
                    "timestamp", fsm.nowIso())));
            humanQueue.closeByTask(taskId, "final_acceptance", new java.util.LinkedHashMap<>(Map.of(
                    "decision", "denied", "reviewer", reviewer, "reason", reason)));
            String action = str(body.getOrDefault("action", "rollback"));
            if ("rollback".equals(action)) {
                Object rollbackToStep = body.get("rollback_to_step");
                String target = firstNonEmpty(body.get("target_agent"), body.get("to_agent"));
                Map<String, Object> rbBody = new java.util.LinkedHashMap<>();
                if (rollbackToStep != null) {
                    rbBody.put("to_step", rollbackToStep);
                }
                if (target != null) {
                    rbBody.put("to_agent", target);
                }
                rbBody.put("reason", reason);
                Result rb = rollback(taskId, task, rbBody, reason);
                if (rb.status() == 200) {
                    fsm.asMap(task.get("fsm")).remove("human_queue_id");
                    fsm.appendHistory(task, "accept_deny_rollback", Map.of("reason", reason));
                    tasks.save(taskId, task);
                    return new Result(200, okBody(task, "accept_deny_rollback", null));
                }
                return rb;
            }
            fsmDoc.put("state", TaskFsmState.BLOCKED.value());
            task.put("status", "failed");
            task.put("error", Map.of("reason", reason, "action", action));
            fsmDoc.remove("human_queue_id");
            fsm.appendHistory(task, "accept_deny", Map.of("reason", reason));
            tasks.save(taskId, task);
            return new Result(200, okBody(task, "accept_deny", null));
        }
        return Result.of(400, "invalid_decision", "decision must be approved or denied");
    }

    private Result rollback(String taskId, Map<String, Object> task,
                            Map<String, Object> body, String reason) {
        fsm.ensureFsm(task, 50);
        // 原链引用（TaskFsmViews.chain 返回拷贝，列表级 add 必须落回 task.chain）
        Object chainObj = task.get("chain");
        List<Map<String, Object>> chain;
        if (chainObj instanceof List<?> rawList) {
            chain = (List<Map<String, Object>>) (List<?>) rawList;
        } else {
            chain = new ArrayList<>();
            task.put("chain", chain);
        }
        Map<String, Object> active = fsm.activeStep(task);
        if (active == null) {
            return Result.of(400, "no_active_step", null);
        }
        Map<String, Object> target = null;
        Object toStep = body.get("to_step");
        String toAgent = firstNonEmpty(body.get("to_agent"), body.get("to_person"));
        if (toStep != null) {
            int sn = intOr(toStep, -1);
            for (Map<String, Object> s : chain) {
                if (intOr(s.get("step"), 0) == sn) {
                    target = s;
                    break;
                }
            }
        } else if (toAgent != null) {
            for (int i = chain.size() - 1; i >= 0; i--) {
                Map<String, Object> s = chain.get(i);
                if (toAgent.equals(str(s.get("to_person")))
                        && StepFsmState.COMPLETED.value().equals(str(s.get("fsm_state")))) {
                    target = s;
                    break;
                }
            }
        }
        if (target == null) {
            return Result.of(400, "rollback_target_not_found", null);
        }

        active.put("fsm_state", StepFsmState.FAILED.value());
        active.put("status", "failed");
        active.put("completed_at", fsm.nowIso());
        if (!reason.isEmpty()) {
            active.put("fail_reason", reason);
        }
        int activeIdx = chain.indexOf(active);
        for (int i = activeIdx + 1; i < chain.size(); i++) {
            chain.get(i).put("fsm_state", StepFsmState.SUPERSEDED.value());
            chain.get(i).put("status", "done");
        }

        int sn = intOr(target.get("step"), 1);
        int attempt = intOr(chain.get(chain.size() - 1).get("attempt"), 1) + 1;
        String stepId = "s" + sn + "a" + attempt;
        Map<String, Object> nxt = new LinkedHashMap<>();
        nxt.put("step", sn);
        nxt.put("step_id", stepId);
        nxt.put("attempt", attempt);
        nxt.put("role_type", target.get("role_type"));
        nxt.put("from_person", str(active.get("to_person")));
        nxt.put("to_agent", str(target.get("to_agent")));
        nxt.put("to_person", str(target.get("to_person")));
        nxt.put("status", "running");
        nxt.put("fsm_state", StepFsmState.QUEUED.value());
        nxt.put("started_at", fsm.nowIso());
        nxt.put("completed_at", null);
        nxt.put("report", null);
        nxt.put("result_consumed", false);
        nxt.put("task_id", taskId);
        nxt.put("result_ref", "msg-results/" + taskId + "/step-" + stepId + ".json");
        nxt.put("rollback_from", str(active.get("step_id")));
        if (!reason.isEmpty()) {
            nxt.put("rollback_reason", reason);
        }
        chain.add(nxt);

        Map<String, Object> fsmDoc = fsm.asMap(task.get("fsm"));
        task.put("assignee", nxt.get("to_person"));
        fsmDoc.put("state", TaskFsmState.EXECUTING.value());
        fsmDoc.put("active_step_id", stepId);
        task.put("status", "running");
        fsm.appendHistory(task, "rollback", Map.of(
                "to_step", target.get("step"),
                "to_person", str(target.get("to_person")),
                "reason", reason,
                "new_step_id", stepId));
        tasks.save(taskId, task);

        Boolean dispatchOk = null;
        if (dispatcher.dispatchStep(task, nxt, reason.isEmpty() ? str(task.get("summary")) : reason)) {
            dispatchOk = true;
            tasks.save(taskId, task);
        } else {
            dispatchOk = false;
        }
        Map<String, Object> out = okBody(task, "rollback", null);
        out.put("dispatch_ok", dispatchOk);
        return new Result(200, out);
    }

    private Result ok(Map<String, Object> task, String action, Map<String, Object> extra) {
        return new Result(200, okBody(task, action, extra));
    }

    private Map<String, Object> okBody(Map<String, Object> task, String action,
                                       Map<String, Object> extra) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("action", action);
        out.put("fsm", fsm.fsmSummary(task));
        if (extra != null) {
            out.putAll(extra);
        }
        return out;
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> plannedChain(Map<String, Object> envelope) {
        Object obj = envelope.get("planned_chain");
        List<Map<String, Object>> out = new ArrayList<>();
        if (obj instanceof List<?> list) {
            for (Object o : list) {
                if (o instanceof Map<?, ?> m) {
                    out.add((Map<String, Object>) m);
                }
            }
        }
        return out;
    }

    private static List<Integer> intList(Object o) {
        List<Integer> out = new ArrayList<>();
        if (o instanceof List<?> list) {
            for (Object v : list) {
                out.add(intOr(v, 0));
            }
        }
        return out;
    }

    private static Map<String, Object> orNewMap(Object o) {
        return o instanceof Map<?, ?> m ? new LinkedHashMap<>((Map<String, Object>) m) : new LinkedHashMap<>();
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
        return null;
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
