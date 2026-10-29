package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 商前 intake（批 A5，2026-10-29）— python handlers_intake 对等：
 * GET /api/intake · /api/intake/{id} · /api/intake/{id}/tasks。
 * 存储：store/leads/order-intake.json（列表，intake_id 为键）。
 *
 * <p>显式偏差（登记）：POST spawn/spawn-analyze（任务桥接生成）与
 * intake gates approve/deny（workflow 引擎 intake 变体）第一版显式 501。
 */
@RestController
public class IntakeController {

    private final Path dataDir;
    private final TaskRepository tasks;

    public IntakeController(Environment env, TaskRepository tasks) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
    }

    /** GET /api/intake — intake 列表。 */
    @GetMapping("/api/intake")
    public Map<String, Object> list() {
        List<Map<String, Object>> items = loadAll();
        return Map.of("status", "ok", "intakes", items, "count", items.size());
    }

    /** GET /api/intake/{id} — 单条详情。 */
    @GetMapping("/api/intake/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable("id") String intakeId) {
        Map<String, Object> intake = find(intakeId);
        if (intake == null) {
            return ResponseEntity.status(404).body(Map.of("status", "error", "error", "not_found"));
        }
        return ResponseEntity.ok(Map.of("status", "ok", "intake", intake));
    }

    /** GET /api/intake/{id}/tasks — pipeline_link 三键关联任务。 */
    @GetMapping("/api/intake/{id}/tasks")
    public ResponseEntity<Map<String, Object>> tasks(@PathVariable("id") String intakeId) {
        Map<String, Object> intake = find(intakeId);
        if (intake == null) {
            return ResponseEntity.status(404).body(Map.of("status", "error", "error", "not_found"));
        }
        Map<String, Object> link = intake.get("pipeline_link") instanceof Map<?, ?> l ? cast(l) : Map.of();
        List<Map<String, Object>> out = new ArrayList<>();
        for (String key : List.of("intake_task_id", "solution_task_id", "content_task_id")) {
            Object tid = link.get(key);
            if (tid == null || String.valueOf(tid).isEmpty()) {
                continue;
            }
            var task = tasks.find(String.valueOf(tid));
            if (task.isPresent()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("link_key", key);
                item.put("task_id", tid);
                item.put("task", task.get());
                out.add(item);
            }
        }
        return ResponseEntity.ok(Map.of("status", "ok", "intake_id", intakeId, "tasks", out));
    }

    /** POST /api/intake/{id}/spawn — 任务桥接生成（java 第一版未对等）。 */
    @PostMapping("/api/intake/{id}/spawn")
    public ResponseEntity<Map<String, Object>> spawn(@PathVariable("id") String intakeId) {
        return notImplemented("intake spawn（任务桥接生成）");
    }

    /** POST /api/intake/spawn-analyze — 同上。 */
    @PostMapping("/api/intake/spawn-analyze")
    public ResponseEntity<Map<String, Object>> spawnAnalyze() {
        return notImplemented("intake spawn-analyze");
    }

    /** POST /api/intake/{id}/gates/{gate}/approve|deny — intake 门禁（第一版 501，python 路由拆分式对齐）。 */
    @PostMapping("/api/intake/{id}/gates/{gate_id}/approve")
    public ResponseEntity<Map<String, Object>> gateApprove(@PathVariable("id") String intakeId,
                                                           @PathVariable("gate_id") String gateId) {
        return notImplemented("intake gates approve");
    }

    @PostMapping("/api/intake/{id}/gates/{gate_id}/deny")
    public ResponseEntity<Map<String, Object>> gateDeny(@PathVariable("id") String intakeId,
                                                        @PathVariable("gate_id") String gateId) {
        return notImplemented("intake gates deny");
    }

    private static ResponseEntity<Map<String, Object>> notImplemented(String what) {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java " + what + " 未对等（批 A5 显式登记）"));
    }

    private List<Map<String, Object>> loadAll() {
        Path p = dataDir.resolve("leads/order-intake.json");
        List<Map<String, Object>> items = new ArrayList<>();
        if (JsonFiles.readMap(p) != null) {
            // 该文件是顶层数组；readMap 仅适对象——用 readTree 走数组
        }
        try {
            var tree = JsonFiles.readTree(p);
            if (tree != null && tree.isArray()) {
                for (var node : tree) {
                    Object plain = JsonFiles.toPlain(node);
                    if (plain instanceof Map<?, ?> m) {
                        items.add(cast(m));
                    }
                }
            }
        } catch (RuntimeException ignored) {
            // 文件缺失/损坏 → 空列表（python json_read 默认同语义）
        }
        return items;
    }

    private Map<String, Object> find(String intakeId) {
        for (Map<String, Object> item : loadAll()) {
            if (intakeId.equals(String.valueOf(item.get("intake_id")))) {
                return item;
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
