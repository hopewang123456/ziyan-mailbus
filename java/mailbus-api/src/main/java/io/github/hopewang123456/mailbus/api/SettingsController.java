package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.SettingsAdminService;
import io.github.hopewang123456.mailbus.app.SharedRoots;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/**
 * 设置中心（批 A4，2026-10-29）— python handlers_settings 对等：
 * GET /api/settings/sections · /api/settings/section/{section} ·
 * /api/settings/env · /api/settings/compose-files ·
 * POST /api/settings/section/{section} · /api/settings/env。
 *
 * <p>显式偏差（登记）：agents/launch_ports/asset_paths/device_bridge 的 patch
 * 与 services probe 第一版未对等（返 400/501）；integrations 走骨架（java 无插件机制）。
 */
@RestController
public class SettingsController {

    private final SettingsAdminService admin;
    private final Environment env;

    public SettingsController(Environment env) {
        Path dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        Path mailbusRoot = SharedRoots.resolve(env.getProperty("mailbus.root"));
        this.admin = new SettingsAdminService(dataDir, mailbusRoot);
        this.env = env;
    }

    /** GET /api/settings/sections — 分节目录。 */
    @GetMapping("/api/settings/sections")
    public Map<String, Object> sections() {
        return Map.of("status", "ok", "sections", admin.listSections());
    }

    /** GET /api/settings/section/{section} — 分节读取。 */
    @GetMapping("/api/settings/section/{section}")
    public ResponseEntity<Map<String, Object>> sectionGet(@PathVariable("section") String section) {
        try {
            return ResponseEntity.ok(Map.of("status", "ok",
                    "section", admin.getSection(section).get("section"),
                    "data", admin.getSection(section).get("data")));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "error", "error", String.valueOf(e.getMessage())));
        }
    }

    /** POST /api/settings/section/{section} — 分节 patch（body.patch 或直接对象）。 */
    @PostMapping("/api/settings/section/{section}")
    public ResponseEntity<Map<String, Object>> sectionPatch(@PathVariable("section") String section,
                                                            @RequestBody Map<String, Object> body) {
        Map<String, Object> patch = body.get("patch") instanceof Map<?, ?> p
                ? cast(p) : body;
        try {
            return ResponseEntity.ok(admin.patchSection(section, patch));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("status", "error", "error", String.valueOf(e.getMessage())));
        } catch (UnsupportedOperationException e) {
            return ResponseEntity.status(400).body(Map.of("status", "error",
                    "error", "not_supported", "detail", String.valueOf(e.getMessage())));
        }
    }

    /** GET /api/settings/env — 环境变量状态（分组，secret 不回值）。 */
    @GetMapping("/api/settings/env")
    public Map<String, Object> envGet() {
        return admin.envStatus();
    }

    /** POST /api/settings/env — 白名单键写 .env。 */
    @PostMapping("/api/settings/env")
    public ResponseEntity<Map<String, Object>> envPatch(@RequestBody Map<String, Object> body) {
        Map<String, Object> vars = body.get("vars") instanceof Map<?, ?> v ? cast(v) : body;
        try {
            return ResponseEntity.ok(admin.patchEnv(vars));
        } catch (IllegalStateException e) {
            return ResponseEntity.status(500).body(Map.of("status", "error", "error", String.valueOf(e.getMessage())));
        }
    }

    /** GET /api/settings/paths — 常用路径（python mailbus_paths 形状对齐）。 */
    @GetMapping("/api/settings/paths")
    public Map<String, Object> paths() {
        // MAILBUS_ROOT=仓根（store 的上上级）；python os.environ["MAILBUS_ROOT"] 同语义
        String root = envOr("MAILBUS_ROOT", "");
        if (root.isEmpty()) {
            Path dd = dataDirPath();
            root = dd.getParent() == null ? String.valueOf(dd)
                    : String.valueOf(dd.getParent().getParent() == null ? dd.getParent() : dd.getParent().getParent());
        }
        root = root.replace("/", "\\");
        String compose = root + "\\docker-agents";
        java.util.Map<String, Object> paths = new java.util.LinkedHashMap<>();
        paths.put("root", root);
        paths.put("mail_dir", envOr("MAIL_DIR", root));
        paths.put("data_dir", envOr("MAILBUS_DATA", root + "\\store"));
        paths.put("compose_dir", compose);
        paths.put("scripts_dir", root + "\\python\\scripts");
        paths.put("team_pack_root", envOr("TEAM_PACK_ROOT", root + "\\team-pack"));
        paths.put("openclaw_workspace", envOr("OPENCLAW_WORKSPACE", ""));
        paths.put("opencode_root", envOr("OPENCODE_ROOT", ""));
        paths.put("node_modules", envOr("NODE_MODULES", ""));
        paths.put("hermes_data", envOr("HERMES_DATA", ""));
        paths.put("codex_workspace", envOr("CODEX_WORKSPACE", ""));
        paths.put("codex_home", envOr("CODEX_HOME", ""));
        paths.put("dsh_workspace", envOr("DSH_WORKSPACE", ""));
        paths.put("skills_root", envOr("MAILBUS_SKILLS_ROOT", root + "\\skills"));
        paths.put("rules_root", envOr("MAILBUS_RULES_ROOT", root + "\\rules"));
        paths.put("plans_root", envOr("MAILBUS_PLANS_ROOT", root + "\\plans"));
        paths.put("docs_root", envOr("MAILBUS_DOCS_ROOT", root + "\\docs"));
        paths.put("identities_root", envOr("MAILBUS_IDENTITIES_ROOT", root + "\\identities"));
        paths.put("api_port", envOr("MAILBUS_API_PORT", "9814"));
        paths.put("compose_project", envOr("COMPOSE_PROJECT_NAME", "mailbus"));
        Path fixPs1 = java.nio.file.Path.of(root, "windows", "fix-wsl-localhost.ps1");
        paths.put("fix_portproxy_ps1", java.nio.file.Files.isRegularFile(fixPs1) ? String.valueOf(fixPs1) : "");
        paths.put("windows_dir", root + "\\windows");
        paths.put("ensure_ollama_ps1", root + "\\tools\\ensure-ollama.py");
        paths.put("run_dir", root + "\\run");
        paths.put("compose_override", envOr("MAILBUS_COMPOSE_OVERRIDE", compose + "\\docker-compose.override.yml"));
        return Map.of(
                "status", "ok",
                "paths", paths,
                "compose_override", paths.get("compose_override"),
                "note", "MAILBUS_*_ROOT / TEAM_PACK_* / MAILBUS_COMPOSE_DIR|OVERRIDE configure these");
    }

    private Path dataDirPath() {
        return SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    private static String envOr(String key, String fallback) {
        String v = System.getenv(key);
        return v == null || v.isEmpty() ? fallback : v;
    }

    /** GET /api/settings/compose-files — compose yml 列表。 */
    @GetMapping("/api/settings/compose-files")
    public Map<String, Object> composeFiles() {
        return Map.of(
                "status", "ok",
                "files", admin.listComposeFiles(),
                "note", "仅加载/编辑/保存 YAML；docker compose / k8s 启停由运维侧执行");
    }

    /** POST /api/settings/section/services/probe — 服务探测（java 第一版未对等）。 */
    @PostMapping("/api/settings/section/services/probe")
    public ResponseEntity<Map<String, Object>> servicesProbe() {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java services probe 未对等（批 A4 显式登记）"));
    }

    /** GET /api/settings/integrations — 可选集成概览（java 无插件机制，空表骨架）。 */
    @GetMapping("/api/settings/integrations")
    public Map<String, Object> integrations() {
        return Map.of(
                "ok", true,
                "count", 0,
                "integrations", List.of(),
                "note", "optional adapters under lib/adapters/integrations/ — not on mailbus core path");
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
