package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.ids.Ids;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * FSM 步骤派发 — python {@code step_dispatch.dispatch_fsm_step} +
 * {@code router/dispatch.dispatch_first_step} 对等（file_bus 路径：写
 * work-order 工单 md + 推 assignee inbox.json；A2A transport_router 与
 * task lock 属 M2b/M2d）。格式与 python 互操作——同一 store 下 agent
 * 无感双栈来源。
 */
public class StepDispatcher {

    private final Path dataDir;
    private final TaskFsmViews fsm;
    /** M2d-b2b：可选 A2A 路由（transport.use_router 开启时远端派发；null=file 直派不变）。 */
    private A2aDispatchRouter a2aRouter;
    private Map<String, Object> agentsConfig = Map.of();

    public StepDispatcher(Path dataDir, Clock clock) {
        this.dataDir = dataDir;
        this.fsm = new TaskFsmViews(clock);
    }

    public void setA2aRouter(A2aDispatchRouter router, Map<String, Object> agentsConfig) {
        this.a2aRouter = router;
        this.agentsConfig = agentsConfig == null ? Map.of() : agentsConfig;
    }

    /**
     * 推 chain[0] 到 assignee inbox 并标记 dispatched。
     * 就地变更 task（step.fsm_state→dispatched + updated_at）；落盘由调用方负责。
     */
    public boolean dispatchFirstStep(Map<String, Object> task) {
        List<Map<String, Object>> chain = TaskFsmViews.chain(task);
        if (chain.isEmpty()) {
            return false;
        }
        return dispatchStep(task, chain.get(0), str(task.get("intent")));
    }

    /** 推指定步骤（rollback 重做步复用）。 */
    public boolean dispatchStep(Map<String, Object> task, Map<String, Object> step, String summary) {
        // M2d-b2b：use_router 开启且 agent 有远端 endpoint → a2a 远端派发；失败回落 file
        if (a2aRouter != null) {
            var outcome = a2aRouter.tryDispatch(task, step, agentsConfig, summary);
            if (outcome.ok()) {
                step.put("fsm_state", io.github.hopewang123456.mailbus.domain.task.StepFsmState.DISPATCHED.value());
                step.put("status", "running");
                step.putIfAbsent("started_at", fsm.nowIso());
                task.put("updated_at", fsm.nowIso());
                return true;
            }
            if (outcome.attempt() != null) {
                // 失败审计：file 兜底时保留 a2a 尝试记录（python fallback 语义）
                List<Map<String, Object>> attempts = new ArrayList<>();
                attempts.add(outcome.attempt());
                step.put("transport_attempts", attempts);
            }
        }
        String to = firstNonEmpty(step.get("to_person"), step.get("to_agent"));
        if (to == null || to.isEmpty()) {
            return false;
        }
        String taskId = str(task.getOrDefault("task_id", task.get("id")));
        String stepId = str(step.getOrDefault("step_id", "s" + step.get("step")));
        String msgId = Ids.newMessageId();

        // 1) work-order 工单（python write_pipeline_work_order 核心段对等）
        String orderPath = writeWorkOrder(task, step, to, taskId, stepId, msgId, summary);
        if (orderPath == null) {
            return false;
        }

        // 2) inbox 推送（目录缺失 = agent 未注册 → 派发失败，python 同语义）
        String resultRef = str(step.getOrDefault("result_ref",
                "msg-results/" + taskId + "/step-" + stepId + ".json"));
        if (!pushInbox(to, msgId, taskId, step, orderPath, resultRef)) {
            return false;
        }

        // 3) mark dispatched（python mark_step_dispatched）
        step.put("fsm_state", io.github.hopewang123456.mailbus.domain.task.StepFsmState.DISPATCHED.value());
        step.put("status", "running");
        step.putIfAbsent("started_at", fsm.nowIso());
        task.put("updated_at", fsm.nowIso());
        return true;
    }

    private String writeWorkOrder(Map<String, Object> task, Map<String, Object> step, String to,
                                  String taskId, String stepId, String msgId, String summary) {
        List<Map<String, Object>> chain = TaskFsmViews.chain(task);
        int stepNum = intOr(step.get("step"), 1);
        Path orderPath = dataDir.resolve("work-orders").resolve(taskId).resolve("step-" + stepId + ".md");
        Path resultFile = dataDir.resolve("msg-results").resolve(taskId).resolve("step-" + stepId + ".json");

        String intent = summary != null && !summary.isEmpty() ? summary : str(task.get("intent"));
        if (intent.length() > 300) {
            intent = intent.substring(0, 300);
        }
        String roleType = step.get("role_type") != null ? String.valueOf(step.get("role_type")) : "";
        // 下一步执行人（python work_order：planned_agents[0] / planned_role_types[0]，
        // 无则「(末步)」）
        String nextPerson = "(末步)";
        if (step.get("planned_agents") instanceof List<?> pa && !pa.isEmpty()) {
            nextPerson = str(pa.get(0));
        } else if (step.get("planned_role_types") instanceof List<?> pr && !pr.isEmpty()) {
            nextPerson = "role_type " + str(pr.get(0));
        }
        String roleTypeSection = roleType.isEmpty() ? "" : """

                ## Role Type
                %s""".formatted(roleType);

        String md = """
                # Pipeline 工单

                <!-- status: in_progress -->

                ---

                ## 巢单元数据
                | 字段 | 值 |
                |------|-----|
                | task_id | %s |
                | step_id | %s |
                | pipeline_step | %d |
                | message_id | %s |
                | 发起人 | mailbus (调度) |
                | 当前执行人 | %s |
                | 下一步执行人 | %s |
                | 状态 | in_progress |
                | result_path | %s |

                ## Intent
                %s

                ## Scope
                当前执行人 %s；必读 store/rules 与 role-flow.json

                ## Acceptance
                写入 `%s`；deliverables 见 `%s`

                ## 本轮 Context
                - 上一步 msg-results 摘要见 pipeline trigger 注入
                - 工单路径：`work-orders/%s/step-%s.md`

                ## On Failure
                写 msg-results conclusion=failed + reason；Dashboard 可 recover --continue
                %s
                ## msg-results 格式（必填）
                ```json
                {
                  "task_id": "%s",
                  "step_id": "%s",
                  "agent": "%s",
                  "role_type": %s,
                  "pipeline_step": %d,
                  "conclusion": "done",
                  "summary": "<本步结论>",
                  "timestamp": "<ISO8601>"
                }
                ```

                ⚠️ 无 msg-results 文件 = 本步未完成。stdout / replies / patch 须经 Delivery Normalizer 归一化后 FSM 才推进。
                """.formatted(taskId, stepId, stepNum, msgId, to, nextPerson,
                resultFile.toAbsolutePath(),
                intent, to, resultFile.toAbsolutePath(),
                dataDir.resolve("deliverables").resolve(taskId).toAbsolutePath(),
                taskId, stepId, roleTypeSection, taskId, stepId, to,
                roleType.isEmpty() ? "0" : roleType, stepNum);
        try {
            Files.createDirectories(orderPath.getParent());
            Files.writeString(orderPath, md);
            // 双轨镜像（python work_order：msg-files/{msg_id}.md 供旧 push 路径解析）
            Path mirror = dataDir.resolve("msg-files").resolve(msgId + ".md");
            Files.createDirectories(mirror.getParent());
            Files.writeString(mirror, md);
            return orderPath.toAbsolutePath().toString();
        } catch (IOException e) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private boolean pushInbox(String to, String msgId, String taskId, Map<String, Object> step,
                              String orderPath, String resultRef) {
        Path inboxFile = dataDir.resolve("inbox").resolve(to).resolve("inbox.json");
        if (!Files.isDirectory(inboxFile.getParent())) {
            return false;
        }
        Map<String, Object> doc = JsonFiles.readMap(inboxFile);
        if (doc == null) {
            doc = new LinkedHashMap<>();
            doc.put("agent", to);
            doc.put("messages", new ArrayList<Map<String, Object>>());
        }
        Object msgsObj = doc.get("messages");
        List<Map<String, Object>> messages = msgsObj instanceof List<?> l ? (List<Map<String, Object>>) (List<?>) l
                : new ArrayList<>();
        int stepNum = intOr(step.get("step"), 1);
        String stepId = str(step.getOrDefault("step_id", "s" + stepNum));
        String content = "📋 【%s】pipeline 步骤 (step_id=%s)\n任务文件: %s\n结果写入: %s\n"
                .formatted(taskId, stepId, orderPath, resultRef)
                + "请读取任务文件执行，完成后写结果文件（含 pipeline_step 与 step_id）。\n\n"
                + "⚠️ 必须写入结果文件才能完成。";
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("id", msgId);
        msg.put("from", "mailbus");
        msg.put("to", to);
        msg.put("type", "task");
        msg.put("priority", "normal");
        msg.put("state", "pending");
        msg.put("task_id", taskId);
        msg.put("pipeline_step", stepNum);
        msg.put("step_id", stepId);
        msg.put("content", content);
        msg.put("created_at", fsm.nowIso());
        messages.add(msg);
        doc.put("messages", messages);
        doc.put("has_unread", true);
        JsonFiles.write(inboxFile, doc);
        return true;
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
