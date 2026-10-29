package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
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
 * 生命周期单条群（批 A7，2026-10-29）— python handlers_lifecycle 对等：
 * GET/POST /api/discover · /api/align · GET /api/agent-profile/{agent} ·
 * /api/search（骨架）· /api/ping/{agent}（骨架）· GET /api/doctor（501）。
 *
 * <p>显式偏差（登记）：discover 无发现源（java 无 DiscoverySource 机制）返空骨架
 * 但保留落盘行为；align 无 merge script 跳过该步（其余 enabled 补齐/agent_count 同构）；
 * agent-profile 第一版仅 profile_paths 显式路径读 identity/soul/skills；
 * search/ping 为骨架（消息存储不同源/launch meta 机制缺失）。
 */
@RestController
public class LifecycleController {

    private static final int EXPECTED_LOCAL_MIN = 13;

    private final Path dataDir;

    public LifecycleController(Environment env) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    /** GET /api/discover — agent 发现报告（java 无发现源，空骨架 + 落盘保留）。 */
    @GetMapping("/api/discover")
    public Map<String, Object> discover() {
        Map<String, Object> report = Map.of("hits", List.of(), "frameworks", List.of(), "count", 0);
        try {
            Files.createDirectories(dataDir.resolve("system"));
            JsonFiles.write(dataDir.resolve("system/discovery-report.json"), report);
        } catch (IOException ignored) {
            // 落盘失败不阻断响应
        }
        // python handler 形状：{"status": "ok", **report}
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.putAll(report);
        return out;
    }

    /** GET/POST /api/align — store 对齐（enabled 补齐 + agent_count 判定；无 merge/发现源）。 */
    @GetMapping("/api/align")
    public Map<String, Object> alignGet() {
        return align(13);
    }

    @PostMapping("/api/align")
    public Map<String, Object> alignPost(@RequestBody(required = false) Map<String, Object> body) {
        int expectMin = 13;
        if (body != null && body.get("expect_min") instanceof Number n) {
            expectMin = n.intValue();
        }
        return align(expectMin);
    }

    private Map<String, Object> align(int expectMin) {
        Path configPath = dataDir.resolve("config.json");
        Map<String, Object> cfg = JsonFiles.readMap(configPath);
        if (cfg == null) {
            cfg = new LinkedHashMap<>();
        }
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : agents.entrySet()) {
            if (e.getValue() instanceof Map<?, ?> ac) {
                Map<String, Object> m = cast(ac);
                if (!m.containsKey("enabled")) {
                    m.put("enabled", false);
                }
            }
        }
        if (!agents.isEmpty()) {
            JsonFiles.write(configPath, cfg);
        }
        int n = agents.size();
        boolean ok = n >= expectMin;
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", ok);
        out.put("agent_count", n);
        out.put("expect_min", expectMin);
        out.put("warning", ok ? null : "aligned agent_count=" + n + " < expect_min=" + expectMin);
        out.put("discovery", Map.of("hits", List.of(), "frameworks", List.of(), "count", 0));
        List<String> ids = new ArrayList<>(agents.keySet());
        ids.sort(String::compareTo);
        out.put("agent_ids", ids);
        return out;
    }

    /** GET /api/agent-profile/{agent} — agent 详情（config + profile_paths 显式文件读）。 */
    @GetMapping("/api/agent-profile/{agent}")
    public ResponseEntity<Map<String, Object>> agentProfile(@PathVariable("agent") String agent) {
        Map<String, Object> cfg = readConfig();
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        Object ac = agents.get(agent);
        if (!(ac instanceof Map<?, ?>)) {
            return ResponseEntity.status(404).body(Map.of("error", "not found"));
        }
        Map<String, Object> agentCfg = cast((Map<?, ?>) ac);
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("name", agent);
        profile.put("config", agentCfg);
        profile.put("identity", readFileHead(agentCfg, "identity", 12000));
        profile.put("soul", readFileHead(agentCfg, "soul", 12000));
        List<Map<String, Object>> skills = new ArrayList<>();
        if (agentCfg.get("skill_groups") instanceof List<?> groups) {
            for (Object g : groups) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("group", g);
                skills.add(row);
            }
        }
        profile.put("skills", skills);
        return ResponseEntity.ok(profile);
    }

    /** GET /api/search — 检索（java 消息存储不同源，空结果骨架对形状）。 */
    @GetMapping("/api/search")
    public Map<String, Object> search(@RequestParam(required = false) String q) {
        return Map.of("messages", List.of(), "count", 0);
    }

    /** GET /api/ping/{agent} — 在线状态骨架（java 无 launch meta/在线探测机制）。 */
    @GetMapping("/api/ping/{agent}")
    public ResponseEntity<Map<String, Object>> ping(@PathVariable("agent") String agent) {
        Map<String, Object> cfg = readConfig();
        Map<String, Object> agents = cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        if (!agents.containsKey(agent)) {
            return ResponseEntity.status(404).body(Map.of("error", "not found", "agent", agent));
        }
        return ResponseEntity.ok(Map.of(
                "agent", agent,
                "online", false,
                "browser", Map.of("ok", false, "note", "java 无 launch 探测机制（批 A7 登记）")));
    }

    /** GET /api/doctor — 诊断报告（python 机制重，501 登记）。 */
    @GetMapping("/api/doctor")
    public ResponseEntity<Map<String, Object>> doctor() {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java doctor 诊断未对等（批 A7 显式登记）"));
    }

    private Map<String, Object> readConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        return cfg == null ? Map.of() : cfg;
    }

    /** profile_paths.<key> 显式路径读文件头 N 字符（python identity/soul 读法）。 */
    private String readFileHead(Map<String, Object> agentCfg, String key, int maxChars) {
        Object paths = agentCfg.get("profile_paths");
        if (!(paths instanceof Map<?, ?> pm)) {
            return null;
        }
        Object p = pm.get(key);
        if (p == null || String.valueOf(p).isBlank()) {
            return null;
        }
        Path f = Path.of(String.valueOf(p));
        if (!Files.isRegularFile(f)) {
            return null;
        }
        try {
            String content = Files.readString(f, StandardCharsets.UTF_8);
            return content.length() > maxChars ? content.substring(0, maxChars) : content;
        } catch (IOException ignored) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
