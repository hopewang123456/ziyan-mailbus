package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.WorkflowsService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 工作流模板端点（交接③，python handlers_workflows 对等）：
 * GET /api/workflows · GET /api/workflows/{id} ·
 * POST /api/workflows/{id} {workflow} · POST /api/workflows/{id}/delete。
 */
@RestController
public class WorkflowsController {

    private final WorkflowsService workflows;

    public WorkflowsController(WorkflowsService workflows) {
        this.workflows = workflows;
    }

    @GetMapping("/api/workflows")
    public Map<String, Object> list() {
        return workflows.list();
    }

    @GetMapping("/api/workflows/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable("id") String id) {
        Map<String, Object> wf = workflows.get(id);
        if (wf == null) {
            return ResponseEntity.status(404).body(Map.of("status", "error", "error", "not_found"));
        }
        return ResponseEntity.ok(Map.of("status", "ok", "workflow_id", id, "workflow", wf));
    }

    @PostMapping("/api/workflows/{id}")
    public ResponseEntity<Map<String, Object>> save(@PathVariable("id") String id,
                                                    @RequestBody Map<String, Object> body) {
        Object wf = body == null ? null : body.get("workflow");
        @SuppressWarnings("unchecked")
        Map<String, Object> workflow = wf instanceof Map<?, ?> m ? (Map<String, Object>) m : null;
        Map<String, Object> out = workflows.save(id, workflow);
        out.remove("__http");
        return ResponseEntity.status(WorkflowsService.httpOf(out)).body(out);
    }

    @PostMapping("/api/workflows/{id}/delete")
    public ResponseEntity<Map<String, Object>> delete(@PathVariable("id") String id) {
        Map<String, Object> out = workflows.delete(id);
        out.remove("__http");
        return ResponseEntity.status(WorkflowsService.httpOf(out)).body(out);
    }
}
