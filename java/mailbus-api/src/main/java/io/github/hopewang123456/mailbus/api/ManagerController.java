package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.TaskFsmViews;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 管理者视图（批 A 第一组，2026-10-29）— python
 * {@code handlers_tasks.handle_human_queue} 与
 * {@code application.queries.manager.manager_pending} 对等：
 * GET /api/human-queue · GET /api/manager/pending。
 */
@RestController
public class ManagerController {

    private static final java.util.Set<String> TERMINAL_STEP_STATES =
            java.util.Set.of("completed", "skipped", "superseded");

    private final Path dataDir;
    private final TaskRepository tasks;
    private final io.github.hopewang123456.mailbus.app.PositionCatalogService positions;

    public ManagerController(Environment env, TaskRepository tasks) {
        this.dataDir = io.github.hopewang123456.mailbus.app.SharedRoots
                .resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
        this.positions = new io.github.hopewang123456.mailbus.app.PositionCatalogService(this.dataDir);
    }

    /** GET /api/human-queue — 人工待办列表（status/type/task_id/intake_id/limit/offset）。 */
    @GetMapping("/api/human-queue")
    public ResponseEntity<Map<String, Object>> humanQueue(
            @RequestParam(defaultValue = "pending") String status,
            @RequestParam(defaultValue = "") String type,
            @RequestParam(defaultValue = "") String taskId,
            @RequestParam(name = "intake_id", defaultValue = "") String intakeId,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        if (limit < 0 || offset < 0) {
            return ResponseEntity.badRequest().body(Map.of("error", "invalid limit/offset"));
        }
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        if (doc == null) {
            doc = Map.of();
        }
        List<Map<String, Object>> all = new ArrayList<>();
        if (doc.get("items") instanceof List<?> l) {
            for (Object o : l) {
                if (o instanceof Map<?, ?> m) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> item = (Map<String, Object>) m;
                    if (!status.isBlank() && !status.equals(str(item.get("status")))) {
                        continue;
                    }
                    if (!type.isBlank() && !type.equals(str(item.get("type")))) {
                        continue;
                    }
                    if (!taskId.isBlank() && !taskId.equals(str(item.get("task_id")))) {
                        continue;
                    }
                    if (!intakeId.isBlank() && !intakeId.equals(str(item.get("intake_id")))) {
                        continue;
                    }
                    all.add(item);
                }
            }
        }
        List<Map<String, Object>> page = all.subList(
                Math.min(offset, all.size()), Math.min(offset + limit, all.size()));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("version", doc.get("version") == null ? "1.0.0" : doc.get("version"));
        out.put("updated_at", doc.get("updated_at") == null ? "" : doc.get("updated_at"));
        out.put("total", all.size());
        out.put("items", page);
        return ResponseEntity.ok(out);
    }

    /** GET /api/manager/pending — 三桶待管理者处理聚合（python manager_pending 对等）。 */
    @GetMapping("/api/manager/pending")
    public Map<String, Object> managerPending() {
        Map<String, Object> counts = new LinkedHashMap<>();
        counts.put("plan_approval", 0);
        counts.put("acceptance", 0);
        counts.put("coordination", 0);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> task : tasks.listAll()) {
            String bucket = bucketOf(task);
            if (bucket.isEmpty()) {
                continue;
            }
            Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> f ? cast(f) : Map.of();
            counts.put(bucket, ((Number) counts.get(bucket)).intValue() + 1);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("task_id", task.get("task_id"));
            item.put("summary", firstNonEmpty(task.get("summary"), task.get("intent")));
            item.put("task_type", task.get("task_type"));
            item.put("initiator", task.get("initiator"));
            item.put("tier", task.get("tier"));
            item.put("priority", fsm.get("priority"));
            item.put("status", task.get("status"));
            item.put("fsm_state", fsm.get("state"));
            item.put("fsm_substate", fsm.get("substate"));
            item.put("fsm_reason", fsm.get("reason"));
            item.put("join_pending", fsm.get("join_pending") instanceof Map<?, ?> jp ? cast(jp) : null);
            item.put("bucket", bucket);
            item.put("current_step", currentStep(task));
            item.put("updated_at", task.get("updated_at"));
            item.put("suggested_actions", suggestedActions(bucket, fsm));
            items.add(item);
        }
        items.sort(Comparator
                .comparing((Map<String, Object> it) -> it.get("priority") instanceof Number n
                        ? n.intValue() : 50)
                .thenComparing(it -> str(it.get("updated_at"))));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("total", items.size());
        out.put("counts", counts);
        out.put("items", items);
        return out;
    }

    private static String bucketOf(Map<String, Object> task) {
        Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> f ? cast(f) : Map.of();
        String state = str(fsm.get("state"));
        String substate = str(fsm.get("substate"));
        if ("accepting".equals(state)) {
            return "acceptance";
        }
        if ("await_plan_approval".equals(substate)) {
            return "plan_approval";
        }
        if ("await_join_review".equals(substate) || "join_gate_review".equals(str(fsm.get("reason")))) {
            return "coordination";
        }
        if ("blocked".equals(state) || "failed".equals(state)) {
            return "coordination";
        }
        return "";
    }

    private static List<String> suggestedActions(String bucket, Map<String, Object> fsm) {
        String substate = str(fsm.get("substate"));
        String reason = str(fsm.get("reason"));
        if ("await_join_review".equals(substate) || "join_gate_review".equals(reason)) {
            return List.of("approve-join", "rollback", "cancel");
        }
        return switch (bucket) {
            case "plan_approval" -> List.of("approve-plan", "rollback", "cancel", "priority");
            case "acceptance" -> List.of("accept", "rollback", "cancel");
            default -> List.of("approve-join", "continue", "rollback", "skip", "cancel", "priority");
        };
    }

    /** python _current_step 对等：首个未终结步（terminated=completed/skipped/superseded 跳过）。 */
    private Map<String, Object> currentStep(Map<String, Object> task) {
        for (Map<String, Object> step : TaskFsmViews.chain(task)) {
            String state = str(firstNonEmpty(step.get("fsm_state"), step.get("status")));
            if (TERMINAL_STEP_STATES.contains(state)) {
                continue;
            }
            Object rt = step.get("role_type");
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("step_id", str(firstNonEmpty(step.get("step_id"), step.get("step"))));
            out.put("role_type", rt);
            out.put("role_zh", roleTypeZh(rt));
            out.put("to_agent", str(firstNonEmpty(step.get("to_agent"), step.get("to_person"))));
            out.put("state", state);
            out.put("report", step.get("report"));
            return out;
        }
        return Map.of();
    }

    /** role_type → 中文名（职位表 display.zh；缺失空串，与 python role_type_to_zh 同口径）。 */
    private String roleTypeZh(Object roleType) {
        if (!(roleType instanceof Number n)) {
            return "";
        }
        Object catalog = positions.catalog();
        if (catalog instanceof Map<?, ?> m && m.get("positions") instanceof List<?> list) {
            for (Object o : list) {
                if (o instanceof Map<?, ?> p && p.get("role_type") instanceof Number rn
                        && rn.intValue() == n.intValue()) {
                    Object zh = p.get("name_zh");
                    return zh == null ? "" : str(zh);
                }
            }
        }
        return "";
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static Object firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return v;
            }
        }
        return "";
    }
}
