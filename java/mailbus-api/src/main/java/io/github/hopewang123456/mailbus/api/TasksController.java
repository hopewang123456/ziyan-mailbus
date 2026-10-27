package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.TaskService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.Optional;

/**
 * 任务端点（M2a）— POST /api/tasks/create · GET /api/tasks ·
 * GET /api/tasks/{id} · GET /api/tasks/{id}/fsm · POST /api/tasks/{id}/fsm/{action}。
 * Thin REST surface；全部逻辑在 {@link TaskService}（app 层，python handlers_tasks 对等）。
 */
@RestController
public class TasksController {

    private static final int DEFAULT_LIMIT = 120;

    private final TaskService tasks;

    public TasksController(TaskService tasks) {
        this.tasks = tasks;
    }

    @PostMapping("/api/tasks/create")
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, Object> body) {
        TaskService.Result r = tasks.createFromEnvelope(body);
        return ResponseEntity.status(r.status()).body(r.body());
    }

    @GetMapping("/api/tasks")
    public Map<String, Object> list(@RequestParam(required = false) String status,
                                    @RequestParam(required = false) String assignee,
                                    @RequestParam(defaultValue = "120") int limit,
                                    @RequestParam(defaultValue = "0") int offset) {
        limit = Math.max(1, Math.min(limit, 500));
        offset = Math.max(0, offset);
        return tasks.listTasks(status, assignee, limit, offset);
    }

    @GetMapping("/api/tasks/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable("id") String id) {
        Optional<Map<String, Object>> task = tasks.getTask(id);
        return task.<ResponseEntity<Map<String, Object>>>map(t -> ResponseEntity.ok(Map.of("task", t)))
                .orElseGet(() -> ResponseEntity.status(404).body(Map.of("error", "not_found")));
    }

    @GetMapping("/api/tasks/{id}/fsm")
    public ResponseEntity<Map<String, Object>> fsm(@PathVariable("id") String id) {
        Optional<Map<String, Object>> summary = tasks.fsmSummary(id);
        return summary.<ResponseEntity<Map<String, Object>>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(404).body(Map.of("error", "not_found")));
    }

    @PostMapping("/api/tasks/{id}/fsm/{action}")
    public ResponseEntity<Map<String, Object>> action(@PathVariable("id") String id,
                                                      @PathVariable("action") String action,
                                                      @RequestBody(required = false) Map<String, Object> body) {
        TaskService.Result r = tasks.fsmAction(id, action, body);
        return ResponseEntity.status(r.status()).body(r.body());
    }
}
