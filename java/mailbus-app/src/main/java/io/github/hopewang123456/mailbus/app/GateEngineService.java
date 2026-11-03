package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Workflow 门禁引擎（java 机制深化批五，2026-10-30）— python
 * {@code application/workflow/engine.py} on_gate_approve / on_gate_deny 对等（核心语义）：
 * registry 门定义查找 → 审批校验（已批/FSM 冲突/body 必填）→ 实例状态更新 →
 * hq 关闭（workflow_gate + llm_step_confirm）→ FSM→executing → on_approve 动作
 * （append_phase / set_stage；spawn_phase 链式展开与 execute_tool 子进程登记为偏差）。
 */
public class GateEngineService {

    private final Path dataDir;
    private final TaskRepository tasks;
    private final HumanQueueService humanQueue;
    private final StepDispatcher dispatcher;

    public GateEngineService(Path dataDir, TaskRepository tasks, HumanQueueService humanQueue,
                             StepDispatcher dispatcher) {
        this.dataDir = dataDir;
        this.tasks = tasks;
        this.humanQueue = humanQueue;
        this.dispatcher = dispatcher;
    }

    /** python workflow_ext：task.extensions.mailbus（dict 容错）。 */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> workflowExt(Map<String, Object> task) {
        Object ext = task.get("extensions");
        if (ext instanceof Map<?, ?> e && e.get("mailbus") instanceof Map<?, ?> m) {
            return new LinkedHashMap<>((Map<String, Object>) m);
        }
        return new LinkedHashMap<>();
    }

    private static void saveWorkflowExt(Map<String, Object> task, Map<String, Object> wfExt) {
        Map<String, Object> ext = task.get("extensions") instanceof Map<?, ?> e
                ? new LinkedHashMap<>(cast(e)) : new LinkedHashMap<>();
        ext.put("mailbus", wfExt);
        task.put("extensions", ext);
    }

    /** python load_registry：store/workflow-registry.json。 */
    private Map<String, Object> loadRegistry() {
        Map<String, Object> r = JsonFiles.readMap(dataDir.resolve("workflow-registry.json"));
        return r == null ? Map.of() : r;
    }

    /** python get_workflow。 */
    private static Map<String, Object> getWorkflow(Map<String, Object> registry, String workflowId) {
        if (registry.get("workflows") instanceof Map<?, ?> wfs) {
            return wfs.get(workflowId) instanceof Map<?, ?> wf ? cast(wf) : null;
        }
        return null;
    }

    /** python get_gate_def。 */
    private static Map<String, Object> getGateDef(Map<String, Object> workflow, String gateId) {
        if (workflow == null || !(workflow.get("gates") instanceof List<?> gates)) {
            return null;
        }
        for (Object o : gates) {
            if (o instanceof Map<?, ?> g && gateId.equals(String.valueOf(g.get("gate_id")))) {
                return cast(g);
            }
        }
        return null;
    }

    /** python _gate_inst。 */
    private static Map<String, Object> gateInst(Map<String, Object> wfExt, String gateId) {
        if (wfExt.get("gates") instanceof List<?> gates) {
            for (Object o : gates) {
                if (o instanceof Map<?, ?> g && gateId.equals(String.valueOf(g.get("gate_id")))) {
                    return cast(g);
                }
            }
        }
        return null;
    }

    /** python validate_approve（必填字段：gate 定义 required_inputs）。 */
    private static String validateApprove(Map<String, Object> body, Map<String, Object> gateDef) {
        if (gateDef.get("required_inputs") instanceof List<?> reqs) {
            for (Object o : reqs) {
                String key = String.valueOf(o);
                Object v = body.get(key);
                if (v == null || String.valueOf(v).isBlank()) {
                    return "missing_required: " + key;
                }
            }
        }
        return null;
    }

    /** python validate_deny（reason 必填）。 */
    private static String validateDeny(Map<String, Object> body) {
        if (body.get("reason") == null || String.valueOf(body.get("reason")).isBlank()) {
            return "reason required for deny";
        }
        return null;
    }

    /** python on_gate_approve 核心直译。 */
    public Map<String, Object> approve(String taskId, String gateId, Map<String, Object> body) {
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            return err(404, "not_found");
        }
        Map<String, Object> task = new LinkedHashMap<>(found.get());
        Map<String, Object> wfExt = workflowExt(task);

        Map<String, Object> wf = getWorkflow(loadRegistry(), str(wfExt.get("workflow_id")));
        if (wf == null) {
            return err(404, "not_found");
        }
        Map<String, Object> gateDef = getGateDef(wf, gateId);
        if (gateDef == null) {
            return err(404, "not_found");
        }

        Map<String, Object> inst = gateInst(wfExt, gateId);
        if (inst != null && "approved".equals(str(inst.get("status")))) {
            return err(400, "gate_not_pending");
        }
        Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> f ? cast(f) : new LinkedHashMap<>();
        String fsmGateId = str(fsm.get("gate_id"));
        if (!fsmGateId.isEmpty() && !fsmGateId.equals(gateId)
                && inst != null && !"pending".equals(str(inst.get("status")))) {
            return err(409, "task_fsm_conflict");
        }

        String valErr = validateApprove(body, gateDef);
        if (valErr != null) {
            return err(400, valErr);
        }

        String now = nowIso();
        Map<String, Object> resolution = new LinkedHashMap<>();
        resolution.put("decision", "approved");
        resolution.put("reviewer", strOr(body.get("reviewer"), "human"));
        resolution.put("comment", strOr(body.get("comment"), ""));
        resolution.put("attachments", body.get("attachments") instanceof List<?> l ? l : List.of());
        resolution.put("approved_at", now);

        // 实例更新
        List<Map<String, Object>> gates = wfExt.get("gates") instanceof List<?> gl
                ? new ArrayList<>(castList(gl)) : new ArrayList<>();
        Map<String, Object> target = null;
        for (Map<String, Object> g : gates) {
            if (gateId.equals(str(g.get("gate_id")))) {
                target = g;
                break;
            }
        }
        if (target == null) {
            target = new LinkedHashMap<>();
            target.put("gate_id", gateId);
            gates.add(target);
        }
        target.put("status", "approved");
        target.put("approved_by", resolution.get("reviewer"));
        target.put("approved_at", now);
        wfExt.put("gates", gates);
        saveWorkflowExt(task, wfExt);

        // hq 关闭
        humanQueue.closeByTask(taskId, "workflow_gate", resolution);
        humanQueue.closeByTask(taskId, "llm_step_confirm", resolution);

        // on_approve 动作
        List<Map<String, Object>> actions = new ArrayList<>();
        Map<String, Object> onAp = gateDef.get("on_approve") instanceof Map<?, ?> oa ? cast(oa) : Map.of();
        String action = str(onAp.get("action"));
        if ("append_phase".equals(action)) {
            String phaseId = str(onAp.get("phase_id"));
            if (!phaseId.isEmpty() && wf.get("phases") instanceof List<?> phases) {
                for (Object po : phases) {
                    if (po instanceof Map<?, ?> p && phaseId.equals(str(p.get("id")))) {
                        Map<String, Object> phase = cast(p);
                        List<Integer> roleTypes = appendPhaseSteps(task, phase);
                        wfExt.put("phase", phaseId);
                        saveWorkflowExt(task, wfExt);
                        Map<String, Object> act = new LinkedHashMap<>();
                        act.put("action", "append_phase");
                        act.put("phase_id", phaseId);
                        act.put("role_types", roleTypes);
                        actions.add(act);
                        break;
                    }
                }
            }
        } else if ("spawn_phase".equals(action)) {
            Map<String, Object> act = new LinkedHashMap<>();
            act.put("action", "spawn_phase");
            act.put("phase_id", str(onAp.get("phase_id")));
            act.put("note", "java spawn_phase 链式展开为登记偏差（批五）");
            actions.add(act);
        }
        if (!str(onAp.get("set_stage")).isEmpty()) {
            wfExt.put("stage", onAp.get("set_stage"));
            saveWorkflowExt(task, wfExt);
        }

        // FSM → executing
        Map<String, Object> newFsm = task.get("fsm") instanceof Map<?, ?> f2 ? new LinkedHashMap<>(cast(f2)) : new LinkedHashMap<>();
        newFsm.put("state", "executing");
        newFsm.remove("substate");
        newFsm.remove("gate_id");
        newFsm.remove("human_queue_id");
        task.put("fsm", newFsm);
        task.put("status", "running");

        boolean dispatchOk = false;
        try {
            dispatchOk = dispatcher.dispatchFirstStep(task);
        } catch (Exception ignored) {
            // 派发失败不阻断审批
        }
        if (dispatchOk) {
            Map<String, Object> act = new LinkedHashMap<>();
            act.put("action", "dispatch");
            act.put("ok", true);
            actions.add(act);
        }

        tasks.save(taskId, task);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", true);
        out.put("gate_id", gateId);
        out.put("resolution", resolution);
        out.put("actions", actions);
        out.put("dispatch_ok", dispatchOk);
        return out;
    }

    /** python on_gate_deny 核心直译。 */
    public Map<String, Object> deny(String taskId, String gateId, Map<String, Object> body) {
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            return err(404, "not_found");
        }
        Map<String, Object> task = new LinkedHashMap<>(found.get());
        Map<String, Object> wfExt = workflowExt(task);

        Map<String, Object> wf = getWorkflow(loadRegistry(), str(wfExt.get("workflow_id")));
        Map<String, Object> gateDef = getGateDef(wf == null ? Map.of() : wf, gateId);
        if (wf == null || gateDef == null) {
            return err(404, "not_found");
        }

        String valErr = validateDeny(body);
        if (valErr != null) {
            return err(400, valErr);
        }

        // 实例置 denied
        List<Map<String, Object>> gates = wfExt.get("gates") instanceof List<?> gl
                ? new ArrayList<>(castList(gl)) : new ArrayList<>();
        Map<String, Object> target = null;
        for (Map<String, Object> g : gates) {
            if (gateId.equals(str(g.get("gate_id")))) {
                target = g;
                break;
            }
        }
        if (target == null) {
            target = new LinkedHashMap<>();
            target.put("gate_id", gateId);
            gates.add(target);
        }
        target.put("status", "denied");
        target.put("reason", strOr(body.get("reason"), ""));
        target.put("denied_at", nowIso());
        wfExt.put("gates", gates);
        saveWorkflowExt(task, wfExt);

        String reason = strOr(body.get("reason"), "");
        Map<String, Object> resolution = new LinkedHashMap<>();
        resolution.put("decision", "denied");
        resolution.put("reviewer", strOr(body.get("reviewer"), "human"));
        resolution.put("reason", reason);
        resolution.put("comment", strOr(body.get("comment"), ""));
        humanQueue.closeByTask(taskId, "workflow_gate", resolution);
        humanQueue.closeByTask(taskId, "llm_step_confirm", resolution);

        // on_deny 动作（rollback_phase / set_stage 基本面）
        List<Map<String, Object>> actions = new ArrayList<>();
        Map<String, Object> onDen = gateDef.get("on_deny") instanceof Map<?, ?> od ? cast(od) : Map.of();
        String denyAction = str(onDen.get("action"));
        if ("rollback_phase".equals(denyAction)) {
            wfExt.put("phase", onDen.get("rollback_phase_id"));
            saveWorkflowExt(task, wfExt);
            Map<String, Object> act = new LinkedHashMap<>();
            act.put("action", "rollback_phase");
            act.put("rollback_phase_id", onDen.get("rollback_phase_id"));
            actions.add(act);
        } else if ("replan_llm".equals(denyAction)) {
            Map<String, Object> act = new LinkedHashMap<>();
            act.put("action", "replan_llm");
            act.put("note", "java replan 为登记偏差（批五）");
            actions.add(act);
        }
        if (!str(onDen.get("set_stage")).isEmpty()) {
            wfExt.put("stage", onDen.get("set_stage"));
            saveWorkflowExt(task, wfExt);
        }

        tasks.save(taskId, task);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", true);
        out.put("gate_id", gateId);
        out.put("resolution", resolution);
        out.put("actions", actions);
        return out;
    }

    /** python append_phase_steps：phase.role_types → chain 追加步骤。 */
    private static List<Integer> appendPhaseSteps(Map<String, Object> task, Map<String, Object> phase) {
        List<Integer> out = new ArrayList<>();
        List<Map<String, Object>> chain = task.get("chain") instanceof List<?> cl
                ? new ArrayList<>(castList(cl)) : new ArrayList<>();
        if (phase.get("role_types") instanceof List<?> rts) {
            for (Object rt : rts) {
                if (rt instanceof Number n) {
                    Map<String, Object> step = new LinkedHashMap<>();
                    step.put("step_id", "s" + (chain.size() + 1));
                    step.put("role_type", n.intValue());
                    step.put("fsm_state", "queued");
                    chain.add(step);
                    out.add(n.intValue());
                }
            }
        }
        task.put("chain", chain);
        return out;
    }

    private static Map<String, Object> err(int http, String error) {
        return Map.of("ok", false, "error", error, "http", http);
    }

    private static String nowIso() {
        return OffsetDateTime.now(ZoneId.systemDefault())
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ"));
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static String strOr(Object o, String fallback) {
        String s = str(o);
        return s.isEmpty() ? fallback : s;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> castList(List<?> l) {
        return (List<Map<String, Object>>) (List<?>) l;
    }
}
