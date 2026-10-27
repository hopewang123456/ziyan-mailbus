package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.task.StepFsmState;
import io.github.hopewang123456.mailbus.domain.task.TaskFsmState;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 任务 FSM 视图与公共转移 — python {@code task_fsm.py} 的 ensure_fsm /
 * get_active_step / fsm_summary / _append_history 对等（M2a 子集：不做
 * legacy status 迁移——java 只写规范 fsm 字段；读侧宽松兼容 python 文件）。
 */
public class TaskFsmViews {

    private final Clock clock;

    public TaskFsmViews(Clock clock) {
        this.clock = clock;
    }

    public String nowIso() {
        return Instant.now(clock).toString();
    }

    /** 补全 fsm 字段（幂等）：state/version/priority/history/active_step_id。 */
    public void ensureFsm(Map<String, Object> task, int defaultPriority) {
        Map<String, Object> fsm = asMap(task.get("fsm"));
        if (fsm.isEmpty()) {
            fsm = new LinkedHashMap<>();
            task.put("fsm", fsm);
        }
        if (!fsm.containsKey("state") || str(fsm.get("state")).isEmpty()) {
            String status = str(task.getOrDefault("status", "running")).toLowerCase();
            if ("success".equals(status)) {
                fsm.put("state", TaskFsmState.SUCCEEDED.value());
            } else if ("failed".equals(status)) {
                fsm.put("state", TaskFsmState.FAILED.value());
            } else if ("cancelled".equals(status) || "timeout".equals(status)) {
                fsm.put("state", TaskFsmState.CANCELLED.value());
            } else if ("paused".equals(status)) {
                fsm.put("state", TaskFsmState.PAUSED.value());
            } else {
                fsm.put("state", TaskFsmState.EXECUTING.value());
            }
        }
        fsm.putIfAbsent("version", 1);
        fsm.putIfAbsent("priority", defaultPriority);
        fsm.putIfAbsent("history", new ArrayList<Map<String, Object>>());

        Map<String, Object> active = activeStep(task);
        fsm.put("active_step_id", active != null ? active.get("step_id") : fsm.get("active_step_id"));
    }

    /** 当前活跃步骤：优先 fsm.active_step_id 非终态；否则 chain 逆序第一个非终态。 */
    public Map<String, Object> activeStep(Map<String, Object> task) {
        List<Map<String, Object>> chain = chain(task);
        Map<String, Object> fsm = asMap(task.get("fsm"));
        String aid = str(fsm.get("active_step_id"));
        if (aid != null && !aid.isEmpty()) {
            for (Map<String, Object> step : chain) {
                if (aid.equals(str(step.getOrDefault("step_id", step.get("step"))))) {
                    if (!isTerminalStep(step)) {
                        return step;
                    }
                    break;
                }
            }
        }
        for (int i = chain.size() - 1; i >= 0; i--) {
            if (!isTerminalStep(chain.get(i))) {
                return chain.get(i);
            }
        }
        return chain.isEmpty() ? null : chain.get(chain.size() - 1);
    }

    /** API / Dashboard 状态机摘要（python fsm_summary 对等形状）。 */
    public Map<String, Object> fsmSummary(Map<String, Object> task) {
        ensureFsm(task, 50);
        Map<String, Object> fsm = asMap(task.get("fsm"));
        Map<String, Object> active = activeStep(task);
        List<Map<String, Object>> stepsView = new ArrayList<>();
        for (Map<String, Object> s : chain(task)) {
            Map<String, Object> v = new LinkedHashMap<>();
            v.put("step", s.get("step"));
            v.put("step_id", s.get("step_id"));
            v.put("fsm_state", s.get("fsm_state"));
            v.put("to_role", s.get("to_role"));
            v.put("to_person", s.get("to_person"));
            v.put("attempt", s.getOrDefault("attempt", 1));
            v.put("result_ref", s.get("result_ref"));
            v.put("node_type", s.getOrDefault("node_type", "agent"));
            v.put("automation", s.getOrDefault("automation", "auto"));
            stepsView.add(v);
        }
        Map<String, Object> activeView = null;
        if (active != null) {
            activeView = new LinkedHashMap<>();
            activeView.put("step_id", active.get("step_id"));
            activeView.put("fsm_state", active.get("fsm_state"));
            activeView.put("to_person", active.get("to_person"));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("task_id", task.getOrDefault("task_id", task.get("id")));
        out.put("fsm_state", fsm.get("state"));
        out.put("priority", fsm.getOrDefault("priority", 50));
        out.put("active_step_id", fsm.get("active_step_id"));
        out.put("active_step", activeView);
        out.put("steps", stepsView);
        return out;
    }

    /** 追加历史事件（保底 100 条窗口，python _append_history 对等）。 */
    public void appendHistory(Map<String, Object> task, String event, Map<String, Object> detail) {
        Map<String, Object> fsm = asMap(task.get("fsm"));
        if (fsm.isEmpty()) {
            fsm = new LinkedHashMap<>();
            task.put("fsm", fsm);
        }
        Object histObj = fsm.get("history");
        List<Map<String, Object>> hist = histObj instanceof List<?> l ? new ArrayList<>() : new ArrayList<>();
        if (histObj instanceof List<?> l) {
            for (Object o : l) {
                if (o instanceof Map<?, ?> m) {
                    hist.add(new LinkedHashMap<>((Map<String, Object>) m));
                }
            }
        }
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("at", nowIso());
        entry.put("event", event);
        if (detail != null) {
            entry.putAll(detail);
        }
        hist.add(entry);
        if (hist.size() > 100) {
            hist = new ArrayList<>(hist.subList(hist.size() - 100, hist.size()));
        }
        fsm.put("history", hist);
    }

    public boolean isTerminalStep(Map<String, Object> step) {
        String fs = str(firstNonEmpty(step.get("fsm_state"), step.get("status")));
        return StepFsmState.TERMINAL.contains(fs);
    }

    public static List<Map<String, Object>> chain(Map<String, Object> task) {
        Object chain = task.get("chain");
        List<Map<String, Object>> out = new ArrayList<>();
        if (chain instanceof List<?> list) {
            for (Object o : list) {
                if (o instanceof Map<?, ?> m) {
                    out.add((Map<String, Object>) m);
                }
            }
        }
        return out;
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

    @SuppressWarnings("unchecked")
    public static Map<String, Object> asMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
    }
}
