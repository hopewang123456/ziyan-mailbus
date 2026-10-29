package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.BuiltinIdentitiesService;
import io.github.hopewang123456.mailbus.app.DashboardConfigService;
import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 运维视图端点（批 A3，2026-10-29）— python handlers_system 对等：
 * GET /api/heartbeat · /api/alerts · /api/config ·
 * POST /api/metrics/layout · /api/metrics/rules/{id} ·
 * POST /api/identities/{id} · /api/positions/{role_type}。
 *
 * <p>显式偏差（登记）：python /api/heartbeat 为 per-agent 心跳聚合
 * （_aggregate_daemon_heartbeats），java 第一版直读 heartbeat.json 状态文件。
 */
@RestController
public class OpsViewController {

    /** python metrics rules 编辑白名单（adapters/metrics/rules.py）。 */
    private static final List<String> RULE_PATCH_KEYS = List.of("enabled", "threshold", "severity", "note", "actions");
    /** python 职位编辑白名单（handlers_tasks._POSITION_PATCH_KEYS）。 */
    private static final List<String> POSITION_PATCH_KEYS = List.of("display", "candidates", "inputs", "default_sla_minutes", "key");

    private final Path dataDir;
    private final Path mailbusRoot;
    private final DashboardConfigService dashboard;

    public OpsViewController(Environment env) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.mailbusRoot = SharedRoots.resolve(env.getProperty("mailbus.root"));
        this.dashboard = new DashboardConfigService(dataDir, mailbusRoot);
    }

    /**
     * GET /api/heartbeat — 心跳状态（python heartbeat.load_status 对等）：
     * bus 共享心跳 heartbeat.json + per-agent heartbeat.{agent}.json 聚合
     * （daemon 覆盖同名字段），恒含 agents/health 两键。
     */
    @GetMapping("/api/heartbeat")
    public Map<String, Object> heartbeat() {
        Map<String, Object> bus = JsonFiles.readMap(dataDir.resolve("heartbeat.json"));
        Map<String, Object> agents = new LinkedHashMap<>();
        if (bus != null && bus.get("agents") instanceof Map<?, ?> m) {
            agents.putAll(cast(m));
        }
        // per-agent daemon 心跳聚合（glob heartbeat.*.json，agent 字段为键）
        try (var files = Files.list(dataDir)) {
            files.filter(f -> {
                        String n = f.getFileName().toString();
                        return n.startsWith("heartbeat.") && n.endsWith(".json");
                    })
                    .sorted()
                    .forEach(f -> {
                        Map<String, Object> doc = JsonFiles.readMap(f);
                        Object agent = doc == null ? null : doc.get("agent");
                        if (agent != null && !String.valueOf(agent).isBlank()) {
                            agents.put(String.valueOf(agent), doc);
                        }
                    });
        } catch (Exception ignored) {
            // 目录不可读 → 无 daemon 心跳
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("agents", agents);
        out.put("health", bus != null && bus.get("health") instanceof Map<?, ?> h ? h : Map.of());
        return out;
    }

    /** GET /api/alerts — 最近告警（alerts.json 尾部 50，python get_recent_alerts 对等）。 */
    @GetMapping("/api/alerts")
    public Map<String, Object> alerts() {
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("alerts.json"));
        List<?> all = doc == null || !(doc.get("alerts") instanceof List<?> l) ? List.of() : l;
        int from = Math.max(0, all.size() - 50);
        return Map.of("alerts", all.subList(from, all.size()));
    }

    /** GET /api/config — 总线配置（脱敏：去 token 键，api_token → ***）。 */
    @GetMapping("/api/config")
    public Map<String, Object> config() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        Map<String, Object> safe = new LinkedHashMap<>();
        if (cfg != null) {
            for (Map.Entry<String, Object> e : cfg.entrySet()) {
                if (e.getKey().equals("token")) {
                    continue;
                }
                safe.put(e.getKey(), e.getValue());
            }
        }
        if (safe.get("api_token") != null) {
            safe.put("api_token", "***");
        }
        return safe;
    }

    /** POST /api/metrics/layout — 大盘布局整体覆盖写（body {hidden: [...]}）。 */
    @PostMapping("/api/metrics/layout")
    public ResponseEntity<Map<String, Object>> layoutSave(@RequestBody Map<String, Object> body) {
        List<String> hidden = new ArrayList<>();
        if (body.get("hidden") instanceof List<?> l) {
            for (Object o : l) {
                if (o != null) {
                    hidden.add(String.valueOf(o));
                }
            }
        }
        return ResponseEntity.ok(dashboard.saveLayout(hidden));
    }

    /**
     * POST /api/metrics/rules/{id} — 规则编辑（白名单 enabled/threshold/severity/note/actions；
     * alert-rules.json 覆盖层 + seed 合成视图，python adapters/metrics/rules.patch_rule 对等）。
     */
    @PostMapping("/api/metrics/rules/{id}")
    public ResponseEntity<Map<String, Object>> rulePatch(@PathVariable("id") String ruleId,
                                                         @RequestBody Map<String, Object> body) {
        Map<String, Object> fields = body.get("fields") instanceof Map<?, ?> f ? cast(f) : body;
        List<String> unknown = new ArrayList<>();
        for (String k : fields.keySet()) {
            if (!RULE_PATCH_KEYS.contains(k)) {
                unknown.add(k);
            }
        }
        if (!unknown.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "fatal", "detail", "不可编辑字段: " + String.join(", ", unknown)));
        }
        // seed 中须存在该规则（python load_rules 判定；java rules() 已含 seed+覆盖合成）
        boolean seeded = dashboard.rules().stream().anyMatch(r -> ruleId.equals(String.valueOf(r.get("id"))));
        if (!seeded) {
            return ResponseEntity.status(404).body(Map.of(
                    "error", "not_found", "detail", "规则 " + ruleId + " 不存在"));
        }
        Path overlay = dataDir.resolve("config/alert-rules.json");
        Map<String, Object> doc = JsonFiles.readMap(overlay);
        List<Map<String, Object>> rules = new ArrayList<>();
        if (doc != null && doc.get("rules") instanceof List<?> l) {
            for (Object o : l) {
                if (o instanceof Map<?, ?> m) {
                    rules.add(cast(m));
                }
            }
        }
        Map<String, Object> hit = rules.stream()
                .filter(r -> ruleId.equals(String.valueOf(r.get("id")))).findFirst().orElse(null);
        if (hit == null) {
            hit = new LinkedHashMap<>();
            hit.put("id", ruleId);
            rules.add(hit);
        }
        hit.putAll(fields);
        if (doc == null) {
            doc = new LinkedHashMap<>();
        }
        doc.put("rules", rules);
        if (doc.get("version") == null) {
            doc.put("version", "1.0.0");
        }
        try {
            Files.createDirectories(overlay.getParent());
        } catch (Exception ignored) {
            // dir exists
        }
        JsonFiles.write(overlay, doc);
        // 合成视图：seed 行 + 覆盖字段
        Map<String, Object> base = dashboard.rules().stream()
                .filter(r -> ruleId.equals(String.valueOf(r.get("id")))).findFirst().orElse(Map.of());
        Map<String, Object> merged = new LinkedHashMap<>(base);
        merged.putAll(hit);
        return ResponseEntity.ok(Map.of("status", "ok", "rule", merged));
    }

    /** POST /api/identities/{id} — 改显示名（BuiltinIdentitiesService.rename；404 语义同 python）。 */
    @PostMapping("/api/identities/{id}")
    public ResponseEntity<Map<String, Object>> identityRename(@PathVariable("id") String identId,
                                                              @RequestBody Map<String, Object> body) {
        String name = body.get("display_name") == null ? "" : String.valueOf(body.get("display_name")).trim();
        Map<String, Object> updated = new BuiltinIdentitiesService(dataDir, mailbusRoot).rename(identId, name);
        if (updated == null) {
            return ResponseEntity.status(404).body(Map.of(
                    "error", "not_found", "detail", "身份 " + identId + " 不存在或名称为空"));
        }
        return ResponseEntity.ok(Map.of("status", "ok", "identity", updated));
    }

    /**
     * POST /api/positions/{role_type} — 职位编辑（白名单 display/candidates/inputs/
     * default_sla_minutes/key；写 roles/json/role-types.json SoT；inputs 校验同 python）。
     */
    @PostMapping("/api/positions/{role_type}")
    public ResponseEntity<Map<String, Object>> positionPatch(@PathVariable("role_type") int roleType,
                                                             @RequestBody Map<String, Object> body) {
        Map<String, Object> fields = body.get("fields") instanceof Map<?, ?> f ? cast(f) : body;
        List<String> unknown = new ArrayList<>();
        for (String k : fields.keySet()) {
            if (!POSITION_PATCH_KEYS.contains(k)) {
                unknown.add(k);
            }
        }
        if (unknown.isEmpty() && fields.get("inputs") instanceof List<?> inputs) {
            String err = validateInputs(inputs);
            if (err != null) {
                return ResponseEntity.badRequest().body(Map.of("error", "fatal", "detail", err));
            }
        }
        if (!unknown.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "fatal", "detail", "不可编辑字段: " + String.join(", ", unknown)));
        }
        Path soT = dataDir.resolve("roles/json/role-types.json");
        Map<String, Object> doc = JsonFiles.readMap(soT);
        if (doc == null || !(doc.get("roles") instanceof Map<?, ?>)) {
            return ResponseEntity.status(404).body(Map.of(
                    "error", "not_found", "detail", "role-types.json 缺失或无 roles"));
        }
        Map<String, Object> roles = doc.get("roles") instanceof Map<?, ?> rm ? cast(rm) : Map.of();
        String key = String.valueOf(roleType);
        Map<String, Object> entry = roles.get(key) instanceof Map<?, ?> m ? cast(m) : null;
        if (entry == null) {
            return ResponseEntity.status(404).body(Map.of(
                    "error", "not_found", "detail", "职位 " + roleType + " 不存在"));
        }
        entry.putAll(fields);
        roles.put(key, entry);
        JsonFiles.write(soT, doc);
        return ResponseEntity.ok(Map.of("status", "ok", "role_type", roleType, "entry", entry));
    }

    /** python _validate_position_inputs 对等：name 必填/type 白名单/enum 需 options。 */
    private static String validateInputs(List<?> inputs) {
        List<String> allowed = List.of("string", "text", "enum", "number", "boolean");
        for (int i = 0; i < inputs.size(); i++) {
            if (!(inputs.get(i) instanceof Map<?, ?> f)) {
                return "inputs[" + i + "] 需为对象";
            }
            String name = f.get("name") == null ? "" : String.valueOf(f.get("name")).trim();
            String type = f.get("type") == null ? "" : String.valueOf(f.get("type")).trim();
            if (name.isEmpty()) {
                return "inputs[" + i + "].name 必填";
            }
            if (!allowed.contains(type)) {
                return "inputs[" + i + "].type 必须是 " + String.join("/", allowed);
            }
            if (type.equals("enum")) {
                Object options = f.get("options");
                if (!(options instanceof List<?> l) || l.isEmpty()) {
                    return "inputs[" + i + "] enum 类型需 options";
                }
            }
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
