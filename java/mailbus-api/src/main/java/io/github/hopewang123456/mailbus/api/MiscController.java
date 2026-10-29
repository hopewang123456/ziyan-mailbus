package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.DemoService;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 面板杂项群（批 A8，2026-10-29）— demo 2 条实现 + 演示/诊所/研发/演练/
 * token/agents 系/tasks 杂项的显式 501（机制重底座，逐条登记）。
 */
@RestController
public class MiscController {

    private final Path dataDir;
    private final TaskRepository tasks;
    private final DemoService demo;
    private final io.github.hopewang123456.mailbus.app.TokenAdminService tokenAdmin;

    public MiscController(Environment env, TaskRepository tasks, InboxService inbox,
                          io.github.hopewang123456.mailbus.app.ArchiveService archive,
                          jakarta.servlet.http.HttpServletRequest request) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
        this.demo = new DemoService(inbox, archive);
        this.tokenAdmin = new io.github.hopewang123456.mailbus.app.TokenAdminService(this.dataDir);
        this.request = request;
    }

    private final jakarta.servlet.http.HttpServletRequest request;

    /** python client_context_from_handler 对等。 */
    private io.github.hopewang123456.mailbus.app.TokenAdminService.ClientContext clientContext() {
        return new io.github.hopewang123456.mailbus.app.TokenAdminService.ClientContext(
                request.getRemoteAddr(),
                request.getHeader("Authorization") == null ? "" : request.getHeader("Authorization"),
                request.getHeader("X-API-Key") == null ? "" : request.getHeader("X-API-Key"));
    }

    /** python live_auth_config 对等（读 store config auth 段）。 */
    private Map<String, Object> liveAuthConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        Map<String, Object> auth = cfg != null && cfg.get("auth") instanceof Map<?, ?> a
                ? new LinkedHashMap<>(cast(a)) : new LinkedHashMap<>();
        return Map.of("auth", (Object) auth);
    }

    /** POST /api/demo/run — 一键演示链（java DemoService：返回叙事行）。 */
    @PostMapping("/api/demo/run")
    public ResponseEntity<Map<String, Object>> demoRun(@RequestBody(required = false) Map<String, Object> body) {
        try {
            List<String> lines = demo.run();
            return ResponseEntity.ok(Map.of(
                    "status", "ok",
                    "ok", true,
                    "steps", lines.size(),
                    "lines", lines));
        } catch (Exception e) {
            return ResponseEntity.status(500).body(Map.of(
                    "status", "error", "error", String.valueOf(e.getMessage())));
        }
    }

    /** POST /api/demo/clean — 清除演示数据（demo 目录删除）。 */
    @PostMapping("/api/demo/clean")
    public ResponseEntity<Map<String, Object>> demoClean() {
        Path dir = dataDir.resolve("demo");
        int removed = 0;
        if (Files.isDirectory(dir)) {
            try (var s = Files.walk(dir)) {
                removed = (int) s.filter(Files::isRegularFile).count();
            } catch (Exception ignored) {
                removed = 0;
            }
            try (var s = Files.walk(dir)) {
                s.sorted(java.util.Comparator.reverseOrder()).forEach(p -> {
                    try {
                        Files.deleteIfExists(p);
                    } catch (Exception ignored) {
                        // 尽力删
                    }
                });
            } catch (Exception ignored) {
                // 尽力删
            }
        }
        return ResponseEntity.ok(Map.of("status", "ok", "removed", removed));
    }

    /** POST /api/tasks/audit — 追加审计记录到任务 audit_log。 */
    @PostMapping("/api/tasks/audit")
    public ResponseEntity<Map<String, Object>> taskAudit(@RequestBody Map<String, Object> body) {
        String taskId = str(body.get("task_id"));
        String reviewer = str(body.get("reviewer"));
        String result = str(body.get("result"));
        if (taskId.isEmpty() || reviewer.isEmpty() || result.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "缺少 task_id/reviewer/result"));
        }
        if (!List.of("pass", "fail", "warn").contains(result)) {
            return ResponseEntity.badRequest().body(Map.of("error", "result 必须是 pass/fail/warn"));
        }
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            return ResponseEntity.status(404).body(Map.of("error", "task_not_found"));
        }
        Map<String, Object> task = new LinkedHashMap<>(found.get());
        List<Map<String, Object>> auditLog = task.get("audit_log") instanceof List<?> l
                ? new java.util.ArrayList<>(castList(l)) : new java.util.ArrayList<>();
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("reviewer", reviewer);
        entry.put("result", result);
        entry.put("at", java.time.OffsetDateTime.now(java.time.ZoneId.of("Asia/Shanghai"))
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ")));
        if (body.get("summary") != null) {
            entry.put("summary", body.get("summary"));
        }
        if (body.get("category") != null) {
            entry.put("category", body.get("category"));
        }
        if (body.get("severity") != null) {
            entry.put("severity", body.get("severity"));
        }
        if (body.get("issues") instanceof List<?> issues) {
            entry.put("issues", issues);
        }
        auditLog.add(entry);
        task.put("audit_log", auditLog);
        tasks.save(taskId, task);
        return ResponseEntity.ok(Map.of("status", "ok", "task_id", taskId, "entry", entry));
    }

    // ── 以下为机制重底座的显式 501（逐条登记，批 A8）──

    @PostMapping("/api/tasks/{id}/gates/{gate_id}/approve")
    public ResponseEntity<Map<String, Object>> taskGateApprove(@PathVariable("id") String id,
                                                               @PathVariable("gate_id") String gateId) {
        return ni("tasks gates approve（workflow engine 未直译）");
    }

    @PostMapping("/api/tasks/{id}/gates/{gate_id}/deny")
    public ResponseEntity<Map<String, Object>> taskGateDeny(@PathVariable("id") String id,
                                                            @PathVariable("gate_id") String gateId) {
        return ni("tasks gates deny（workflow engine 未直译）");
    }

    @GetMapping("/api/tasks/trace")
    public ResponseEntity<Map<String, Object>> taskTrace() {
        return ni("tasks trace（生命周期回放机制）");
    }

    @GetMapping("/api/agents/active")
    public ResponseEntity<Map<String, Object>> agentsActive() {
        return ni("agents active（活跃视图机制）");
    }

    @GetMapping("/api/agents/assembly")
    public ResponseEntity<Map<String, Object>> agentsAssembly() {
        return ni("agents assembly（装配视图机制）");
    }

    @PostMapping("/api/agents/scan")
    public ResponseEntity<Map<String, Object>> agentsScan() {
        return ni("agents scan（发现机制）");
    }

    @PostMapping("/api/agents/recruit")
    public ResponseEntity<Map<String, Object>> agentsRecruit() {
        return ni("agents recruit（招募机制）");
    }

    /** GET /api/config/mailbus-token — ensure + masked status（python handle_mailbus_token GET）。 */
    @GetMapping("/api/config/mailbus-token")
    public ResponseEntity<Map<String, Object>> tokenGet() {
        return ResponseEntity.ok(tokenAdmin.statusView());
    }

    /** POST /api/config/mailbus-token 与 /rotate 同义（python handler POST 分支=rotate）。 */
    @PostMapping("/api/config/mailbus-token")
    public ResponseEntity<Map<String, Object>> tokenPost() {
        return tokenRotate();
    }

    /** POST /api/config/mailbus-token/rotate — 双路径（白名单免旧 token / 其余须出示）。 */
    @PostMapping("/api/config/mailbus-token/rotate")
    public ResponseEntity<Map<String, Object>> tokenRotate() {
        var result = tokenAdmin.rotate(clientContext(), liveAuthConfig());
        if (Boolean.TRUE.equals(result.get("ok"))) {
            return ResponseEntity.ok(Map.of(
                    "status", "ok", "token", result.get("token"), "message", "rotated_once"));
        }
        return ResponseEntity.status(401).body(Map.of(
                "status", "error", "error", "unauthorized",
                "error_code", "unauthorized"));
    }

    @GetMapping("/api/clinic/tools")
    public ResponseEntity<Map<String, Object>> clinicTools() {
        return ni("clinic tools（诊所机制）");
    }

    @GetMapping("/api/clinic/jobs")
    public ResponseEntity<Map<String, Object>> clinicJobs() {
        return ni("clinic jobs（诊所机制）");
    }

    @PostMapping("/api/clinic/run")
    public ResponseEntity<Map<String, Object>> clinicRun() {
        return ni("clinic run（诊所机制）");
    }

    @PostMapping("/api/dev/reload")
    public ResponseEntity<Map<String, Object>> devReload() {
        return ni("dev reload（热重载机制）");
    }

    @PostMapping("/api/drill/video-publish")
    public ResponseEntity<Map<String, Object>> drillVideoPublish() {
        return ni("drill video-publish（演练机制）");
    }

    @GetMapping("/api/internal-llm/status")
    public ResponseEntity<Map<String, Object>> llmStatus() {
        return ni("internal-llm status（python planner 机制）");
    }

    @GetMapping("/api/internal-llm/health")
    public ResponseEntity<Map<String, Object>> llmHealth() {
        return ni("internal-llm health");
    }

    @PostMapping("/api/internal-llm/dry-run")
    public ResponseEntity<Map<String, Object>> llmDryRun() {
        return ni("internal-llm dry-run");
    }

    @PostMapping("/api/internal-llm/rebuild-rag")
    public ResponseEntity<Map<String, Object>> llmRebuildRag() {
        return ni("internal-llm rebuild-rag");

    }

    @GetMapping("/api/demo/trace")
    public ResponseEntity<Map<String, Object>> demoTrace() {
        return ni("demo trace（python demo 链）");
    }

    private static ResponseEntity<Map<String, Object>> ni(String what) {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java " + what + " 未对等（批 A8 显式登记）"));
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> castList(List<?> l) {
        return (List<Map<String, Object>>) (List<?>) l;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
