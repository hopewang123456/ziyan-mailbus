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
    private final io.github.hopewang123456.mailbus.app.CommandDraftService commandDraft;
    private final io.github.hopewang123456.mailbus.app.ClinicAgentService clinic;
    private final org.springframework.core.env.Environment env;

    public MiscController(Environment env, TaskRepository tasks, InboxService inbox,
                          io.github.hopewang123456.mailbus.app.ArchiveService archive,
                          jakarta.servlet.http.HttpServletRequest request) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
        this.demo = new DemoService(inbox, archive);
        this.tokenAdmin = new io.github.hopewang123456.mailbus.app.TokenAdminService(this.dataDir);
        this.commandDraft = new io.github.hopewang123456.mailbus.app.CommandDraftService(
                new io.github.hopewang123456.mailbus.app.TaskPlannerService(this.dataDir, null));
        this.clinic = new io.github.hopewang123456.mailbus.app.ClinicAgentService(this.dataDir);
        this.env = env;
        this.request = request;
        this.gateEngine = new io.github.hopewang123456.mailbus.app.GateEngineService(
                this.dataDir, tasks,
                new io.github.hopewang123456.mailbus.app.HumanQueueService(this.dataDir,
                        java.time.Clock.systemDefaultZone()),
                new io.github.hopewang123456.mailbus.app.StepDispatcher(this.dataDir,
                        java.time.Clock.systemDefaultZone()));
    }

    private final jakarta.servlet.http.HttpServletRequest request;
    private final io.github.hopewang123456.mailbus.app.GateEngineService gateEngine;

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

    /** POST /api/tasks/{id}/gates/{gate_id}/approve — python on_gate_approve 核心直译（批五）。 */
    @PostMapping("/api/tasks/{id}/gates/{gate_id}/approve")
    public ResponseEntity<Map<String, Object>> taskGateApprove(@PathVariable("id") String id,
                                                               @PathVariable("gate_id") String gateId,
                                                               @RequestBody(required = false) Map<String, Object> body) {
        var result = gateEngine.approve(id, gateId, body == null ? Map.of() : body);
        return gateResponse(result);
    }

    /** POST /api/tasks/{id}/gates/{gate_id}/deny — python on_gate_deny 核心直译（批五）。 */
    @PostMapping("/api/tasks/{id}/gates/{gate_id}/deny")
    public ResponseEntity<Map<String, Object>> taskGateDeny(@PathVariable("id") String id,
                                                            @PathVariable("gate_id") String gateId,
                                                            @RequestBody(required = false) Map<String, Object> body) {
        var result = gateEngine.deny(id, gateId, body == null ? Map.of() : body);
        return gateResponse(result);
    }

    private static ResponseEntity<Map<String, Object>> gateResponse(Map<String, Object> result) {
        int http = result.get("http") instanceof Number n ? n.intValue() : (Boolean.TRUE.equals(result.get("ok")) ? 200 : 400);
        Map<String, Object> body = new LinkedHashMap<>(result);
        body.remove("http");
        return ResponseEntity.status(http).body(body);
    }

    /** GET /api/tasks/trace?id= — E9 生命周期回放时序（python task_trace 直译）。 */
    @GetMapping("/api/tasks/trace")
    public ResponseEntity<Map<String, Object>> taskTrace(@org.springframework.web.bind.annotation.RequestParam(required = false) String id) {
        if (id == null || id.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("status", "error", "error", "id required"));
        }
        try {
            return ResponseEntity.ok(new io.github.hopewang123456.mailbus.app.TaskTraceService(dataDir, tasks)
                    .trace(id.trim()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.status(404).body(Map.of("status", "error", "error", String.valueOf(e.getMessage())));
        }
    }

    /** GET /api/agents/active — 三级门禁活跃视图（python list_active_agents 直译）。 */
    @GetMapping("/api/agents/active")
    public Map<String, Object> agentsActive() {
        var active = clinic.activeAgents();
        List<Map<String, Object>> items = new java.util.ArrayList<>();
        for (var e : active.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>((Map<String, Object>) e.getValue());
            row.put("id", e.getKey());
            items.add(row);
        }
        return Map.of("status", "ok", "agents", items);
    }

    /** GET /api/agents/assembly — 装配视图骨架（登记）。 */
    @GetMapping("/api/agents/assembly")
    public Map<String, Object> agentsAssembly() {
        return clinic.agentsAssembly();
    }

    /** POST /api/agents/scan — agent 发现（发现机制，501 登记）。 */
    /** POST /api/agents/scan — config 基本扫描骨架（python DiscoverySource 机制登记偏差）。 */
    @PostMapping("/api/agents/scan")
    public Map<String, Object> agentsScan() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        Map<String, Object> agents = cfg != null && cfg.get("agents") instanceof Map<?, ?> am ? cast(agents0(am)) : Map.of();
        List<Map<String, Object>> hits = new java.util.ArrayList<>();
        for (var e : agents.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("source", "config");
            row.put("id", e.getKey());
            row.put("framework", e.getValue() instanceof Map<?, ?> m ? str(((Map<?, ?>) m).get("type")) : "");
            row.put("enabled", !(e.getValue() instanceof Map<?, ?> m2 && Boolean.FALSE.equals(m2.get("enabled"))));
            hits.add(row);
        }
        return Map.of("status", "ok", "hits", hits, "count", hits.size(),
                "note", "java 无 DiscoverySource 发现机制（仅 config 扫描，批六登记）");
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> agents0(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    /** POST /api/agents/recruit — 招募（LLM 建角色机制，501 登记）。 */
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

    /** GET /api/clinic/tools — 工具清单（形状对齐；执行走 python 工具链）。 */
    @GetMapping("/api/clinic/tools")
    public Map<String, Object> clinicTools() {
        return Map.of("tools", clinic.clinicTools());
    }

    /** GET /api/clinic/jobs — 调度器状态（python _hub_state 形状）。 */
    @GetMapping("/api/clinic/jobs")
    public Map<String, Object> clinicJobs() {
        boolean scanEnabled = Boolean.parseBoolean(String.valueOf(
                env == null ? "true" : env.getProperty("mailbus.task-scan.enabled", "true")));
        return clinic.schedulerStatus(scanEnabled);
    }

    /** POST /api/clinic/run — 执行诊所工具（需 python 工具链，显式 501 登记）。 */
    @PostMapping("/api/clinic/run")
    public ResponseEntity<Map<String, Object>> clinicRun(@RequestBody(required = false) Map<String, Object> body) {
        String toolId = body == null ? "" : str(body.get("tool_id"));
        if (toolId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("ok", false, "error", "tool_id required"));
        }
        return ni("clinic run " + toolId + "（python 工具链）");
    }

    /** POST /api/dev/reload — 配置刷新 ack（java 无 python 插件热重载，返回刷新确认）。 */
    @PostMapping("/api/dev/reload")
    public Map<String, Object> devReload() {
        return Map.of(
                "status", "ok",
                "frameworks", Map.of(),
                "integrations", Map.of(),
                "note", "java 侧配置每次请求即时读取（无缓存需刷新）；插件热重载为 python 机制（批六登记）");
    }

    /** POST /api/drill/video-publish — check-n8n 探测（python run_video_publish_drill check 模式）。 */
    @PostMapping("/api/drill/video-publish")
    public ResponseEntity<Map<String, Object>> drillVideoPublish(@org.springframework.web.bind.annotation.RequestBody(required = false) Map<String, Object> body) {
        String mode = body != null && body.get("mode") != null ? String.valueOf(body.get("mode")).toLowerCase() : "check-n8n";
        if (!mode.contains("n8n")) {
            return ni("drill mode=" + mode + "（完整演练链需 python 工具链）");
        }
        var probe = new io.github.hopewang123456.mailbus.app.TaskTraceService(dataDir, tasks)
                .probeN8nWebhook(System.getenv("N8N_PUBLISH_WEBHOOK_URL"));
        boolean ok = Boolean.TRUE.equals(probe.get("ok"));
        Map<String, Object> step = new LinkedHashMap<>();
        step.put("id", "n8n_probe");
        step.put("status", ok ? "pass" : "fail");
        step.put("detail", probe);
        return ResponseEntity.ok(Map.of(
                "status", ok ? "ok" : "error",
                "ok", ok,
                "mode", "check-n8n",
                "steps", List.of(step),
                "warnings", List.of()));
    }

    /** GET /api/internal-llm/status — python llm_status=probe_all 对等。 */
    @GetMapping("/api/internal-llm/status")
    public Map<String, Object> llmStatus() {
        return new io.github.hopewang123456.mailbus.app.InternalLlmService(dataDir).probeAll();
    }

    /** GET /api/internal-llm/health — 同 status 载荷（python 同源 probe）。 */
    @GetMapping("/api/internal-llm/health")
    public Map<String, Object> llmHealth() {
        return new io.github.hopewang123456.mailbus.app.InternalLlmService(dataDir).probeAll();
    }

    /** POST /api/internal-llm/dry-run — 走 CommandDraftService 预演通道（M2c，不建任务）。 */
    @PostMapping("/api/internal-llm/dry-run")
    public ResponseEntity<Map<String, Object>> llmDryRun(@RequestBody(required = false) Map<String, Object> body) {
        Map<String, Object> env = body != null && body.get("envelope") instanceof Map<?, ?> e ? cast(e)
                : (body == null ? Map.of() : body);
        String intent = str(env.get("intent"));
        if (intent.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "status", "error", "error", "fatal", "message", "缺少 intent"));
        }
        Map<String, Object> r = commandDraft.draft(intent,
                str(env.get("task_type")).isEmpty() ? "custom" : str(env.get("task_type")),
                str(env.get("tier")).isEmpty() ? "M" : str(env.get("tier")));
        int http = ((Number) r.get("status")).intValue();
        @SuppressWarnings("unchecked")
        Map<String, Object> rbody = (Map<String, Object>) r.get("body");
        if (http == 200) {
            return ResponseEntity.ok(Map.of("status", "ok", "result", rbody.get("draft")));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "error");
        out.put("error", rbody.getOrDefault("error", "dry_run_failed"));
        out.put("message", String.valueOf(rbody.getOrDefault("message", "")));
        return ResponseEntity.status(http).body(out);
    }

    /** POST /api/internal-llm/rebuild-rag — chunks 索引重建（python rebuild_index 对等）。 */
    @PostMapping("/api/internal-llm/rebuild-rag")
    public ResponseEntity<Map<String, Object>> llmRebuildRag() {
        try {
            int n = new io.github.hopewang123456.mailbus.app.InternalLlmService(dataDir).rebuildIndex();
            return ResponseEntity.ok(Map.of("status", "ok", "chunks", n));
        } catch (Exception e) {
            return ResponseEntity.status(500).body(Map.of(
                    "status", "error", "error", "rebuild_failed", "message", String.valueOf(e.getMessage())));
        }
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
