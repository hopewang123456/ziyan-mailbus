package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.A2aMessageMapper;
import io.github.hopewang123456.mailbus.app.HumanQueueService;
import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.app.TaskService;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 清单收尾（批 A9，2026-10-29）— 19 条：可直译 5 条（hq-resolve/a2a-tasks/
 * agents-enable/chain-budget GET/harness-report 读）+ 骨架 8 + 501×6。
 * 骨架与 501 的机制差异逐条登记（python 侧专属机制无 java 对应）。
 */
@RestController
public class FinalController {

    private final Path dataDir;
    private final TaskRepository tasks;
    private final TaskService taskService;
    private final HumanQueueService humanQueue;

    public FinalController(Environment env, TaskRepository tasks, TaskService taskService) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
        this.taskService = taskService;
        this.humanQueue = new HumanQueueService(this.dataDir, java.time.Clock.systemDefaultZone());
    }

    // ── 直译 5 条 ──

    /** POST /api/human-queue/{id}/resolve — 审批/驳回（decision 白名单 + 关闭队列项）。 */
    @PostMapping("/api/human-queue/{id}/resolve")
    public ResponseEntity<Map<String, Object>> hqResolve(@PathVariable("id") String itemId,
                                                         @RequestBody Map<String, Object> body) {
        String decision = body.get("decision") == null ? "approved" : String.valueOf(body.get("decision")).toLowerCase();
        if (!decision.equals("approved") && !decision.equals("denied")) {
            return ResponseEntity.badRequest().body(Map.of("error", "decision must be approved or denied"));
        }
        Map<String, Object> resolution = new LinkedHashMap<>();
        resolution.put("decision", decision);
        resolution.put("reviewer", body.get("reviewer") == null ? "dashboard" : body.get("reviewer"));
        resolution.put("comment", firstNonEmpty(body.get("comment"), body.get("reason")));
        resolution.put("reason", body.get("reason") == null ? "" : body.get("reason"));
        // 按 id 定位队列项（task/qtype 维度关闭）
        Map<String, Object> target = null;
        for (Map<String, Object> item : humanQueue.items()) {
            if (itemId.equals(String.valueOf(item.get("id")))) {
                target = item;
                break;
            }
        }
        if (target == null) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found"));
        }
        humanQueue.closeByTask(String.valueOf(target.get("task_id")),
                String.valueOf(target.get("type")), resolution);
        return ResponseEntity.ok(Map.of("status", "ok", "id", itemId, "resolution", resolution));
    }

    /** POST /api/a2a/tasks — 外部 A2A 建任务（A2aMessageMapper + TaskService 创建链路）。 */
    @PostMapping("/api/a2a/tasks")
    public ResponseEntity<Map<String, Object>> a2aTasks(@RequestBody Map<String, Object> body) {
        Map<String, Object> params = body.get("params") instanceof Map<?, ?> p ? cast(p) : body;
        Map<String, Object> envelope = A2aMessageMapper.fromA2aTaskCreate(params);
        var r = taskService.createFromEnvelope(envelope);
        if (r.status() == 201) {
            Map<String, Object> out = new LinkedHashMap<>(r.body());
            out.put("source", "a2a_inbound");
            out.put("envelope", envelope);
            return ResponseEntity.status(201).body(out);
        }
        return ResponseEntity.status(r.status()).body(r.body());
    }

    /** POST /api/agents/{agent}/enable — 启停 agent（写 config.agents.<id>.enabled）。 */
    @PostMapping("/api/agents/{agent}/enable")
    public ResponseEntity<Map<String, Object>> agentEnable(@PathVariable("agent") String agent,
                                                           @RequestBody(required = false) Map<String, Object> body) {
        boolean enable = body == null || !Boolean.FALSE.equals(body.get("enabled"));
        Path configPath = dataDir.resolve("config.json");
        Map<String, Object> cfg = JsonFiles.readMap(configPath);
        Map<String, Object> agents = cfg != null && cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : null;
        if (agents == null || !(agents.get(agent) instanceof Map<?, ?>)) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found",
                    "detail", "agent " + agent + " 未注册"));
        }
        Map<String, Object> ac = cast((Map<?, ?>) agents.get(agent));
        ac.put("enabled", enable);
        JsonFiles.write(configPath, cfg);
        return ResponseEntity.ok(Map.of("status", "ok", "agent", agent, "enabled", enable));
    }

    /** GET /api/chain/budget — 工单链路预算视图（mailbus_chains 段骨架）。 */
    @GetMapping("/api/chain/budget")
    public Map<String, Object> chainBudgetGet() {
        Map<String, Object> cfg = readConfig();
        Map<String, Object> chains = cfg.get("mailbus_chains") instanceof Map<?, ?> c ? cast(c) : Map.of();
        return Map.of("status", "ok",
                "budget", Map.of("chains", chains),
                "llm", Map.of("note", "java 第一版无 ensure_llm_or_prompt（登记）"));
    }

    /** GET /api/harness-reports/{sha} — 审查报告 JSON 读（reports/<sha>*.json 模糊匹配）。 */
    @GetMapping("/api/harness-reports/{sha}")
    public ResponseEntity<Map<String, Object>> harnessReport(@PathVariable("sha") String sha) {
        if (sha.contains("..")) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found"));
        }
        Path dir = dataDir.resolve("harness-reports");
        Path target = null;
        if (Files.isDirectory(dir)) {
            try (var s = Files.list(dir)) {
                var hit = s.filter(f -> f.getFileName().toString().startsWith(sha)
                        && f.getFileName().toString().endsWith(".json")).findFirst();
                if (hit.isPresent()) {
                    target = hit.get();
                }
            } catch (IOException ignored) {
                // 目录读失败 → 404
            }
        }
        if (target == null) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found"));
        }
        Map<String, Object> doc = JsonFiles.readMap(target);
        return doc == null ? ResponseEntity.status(404).body(Map.of("error", "not_found"))
                : ResponseEntity.ok(doc);
    }

    // ── 骨架 8 条（形状对齐，值=机制差异登记）──

    @GetMapping("/api/avatars/manifest")
    public Map<String, Object> avatarsManifest() {
        Map<String, Object> cfg = readConfig();
        List<Map<String, Object>> pairs = new ArrayList<>();
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        for (String aid : agents.keySet()) {
            pairs.add(Map.of(
                    "agent", aid,
                    "portrait_url", "",
                    "animated_url", "",
                    "note", "java 无头像解析机制（批 A9 登记）"));
        }
        return Map.of("status", "ok", "avatars", pairs, "count", pairs.size());
    }

    @GetMapping("/api/external-tools")
    public Map<String, Object> externalTools() {
        return Map.of("status", "ok", "tools", List.of(), "count", 0,
                "note", "java 无外部工具注册表机制（批 A9 登记）");
    }

    @GetMapping("/api/failover/metrics")
    public Map<String, Object> failoverMetrics() {
        return Map.of("status", "ok", "metrics", List.of(), "total", 0,
                "note", "java 无改派指标收集机制（批 A9 登记）");
    }

    @GetMapping("/api/skills/index")
    public Map<String, Object> skillsIndex() {
        return Map.of("status", "ok",
                "index", Map.of("agents", Map.of(), "reverse", Map.of(), "orphans", List.of()),
                "note", "java 无 skills 索引机制（批 A9 登记）");
    }

    @GetMapping("/api/skill-use")
    public Map<String, Object> skillUseGet() {
        return Map.of("status", "ok", "records", List.of(),
                "note", "java 无技能调用记录机制（批 A9 登记）");
    }

    @GetMapping("/api/skill-usage")
    public Map<String, Object> skillUsage() {
        return Map.of("status", "ok", "usage", Map.of(),
                "note", "java 无技能使用统计机制（批 A9 登记）");
    }

    @GetMapping("/api/launch")
    public Map<String, Object> launchList() {
        return Map.of("status", "ok", "agents", Map.of(),
                "note", "java 无 launchable 视图机制（批 A9 登记）");
    }

    @GetMapping("/api/locale/errors")
    public Map<String, Object> localeErrors() {
        return Map.of("ok", true, "errors", Map.of(), "stable_codes", List.of(),
                "note", "java 无错误码中文目录（批 A9 登记）");
    }

    @PostMapping("/api/metrics/snapshot")
    public Map<String, Object> metricsSnapshot() {
        return Map.of("status", "ok", "note", "java 指标即时计算无快照机制（批 A9 登记）");
    }

    // ── 501×6 ──

    @PostMapping("/api/chain/budget")
    public ResponseEntity<Map<String, Object>> chainBudgetPost() {
        return ni("chain budget apply（ollama 决策机制）");
    }

    @PostMapping("/api/launch")
    public ResponseEntity<Map<String, Object>> launchPost() {
        return ni("launch（launch_agent 机制）");
    }

    @PostMapping("/api/skill-use")
    public ResponseEntity<Map<String, Object>> skillUse() {
        return ni("skill-use（技能调用机制）");
    }

    @GetMapping("/api/test-agents")
    public ResponseEntity<Map<String, Object>> testAgents() {
        return ni("test-agents（python 脚本执行）");
    }

    @PostMapping("/api/attachments/upload")
    public ResponseEntity<Map<String, Object>> attachmentsUpload() {
        return ni("attachments upload（multipart 机制）");
    }

    private static ResponseEntity<Map<String, Object>> ni(String what) {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java " + what + " 未对等（批 A9 显式登记）"));
    }

    private Map<String, Object> readConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        return cfg == null ? Map.of() : cfg;
    }

    private static Object firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return v;
            }
        }
        return "";
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
