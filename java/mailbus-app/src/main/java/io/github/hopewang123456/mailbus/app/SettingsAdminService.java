package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 配置中心 admin（批 A4，2026-10-29）— python
 * {@code adapters/config/config_admin.py} 对等（分层直译）：
 * 分节白名单/标签、通用段 get/深合并 patch、env 白名单读写、compose 文件列表。
 *
 * <p>显式偏差（登记）：python 的 agents 段（instance 合成+framework discovery）、
 * services 段探测、asset_paths 双源同步、launch_ports/device_bridge 结构化 patch、
 * internal_llm provider 视图在 java 第一版未对等——agents/launch_ports/asset_paths/
 * device_bridge 的 patch 返 400 not_supported，读取走通用形状。
 */
public class SettingsAdminService {

    /** python EDITABLE_SECTIONS 对等（19 段）。 */
    public static final List<String> EDITABLE_SECTIONS = List.of(
            "mailbus_internal_llm", "mailbus_workflow", "mailbus_automation",
            "mailbus_intake_bridge", "mailbus_device_bridge", "mailbus_codex",
            "mailbus_claude", "mailbus_chains", "scheduler", "agents",
            "frameworks", "launch_ports", "smart_routing", "services",
            "harness", "asset_paths", "browser_hosts", "auth", "composition");

    /** python SECTION_LABELS 对等。 */
    public static final Map<String, String> SECTION_LABELS = Map.ofEntries(
            Map.entry("mailbus_internal_llm", "Internal LLM / Planner"),
            Map.entry("mailbus_workflow", "Workflow & tool_live"),
            Map.entry("mailbus_automation", "自动化边界"),
            Map.entry("mailbus_intake_bridge", "Intake Bridge"),
            Map.entry("mailbus_device_bridge", "Device Bridge / 设备桥"),
            Map.entry("mailbus_codex", "Codex / Desktop 启动"),
            Map.entry("mailbus_claude", "Claude Code / Desktop 启动"),
            Map.entry("mailbus_chains", "工单链路模板 / 日预算"),
            Map.entry("scheduler", "Scheduler 定时任务"),
            Map.entry("agents", "Agent 运行时"),
            Map.entry("frameworks", "Framework enable / 路径"),
            Map.entry("launch_ports", "Launch 端口"),
            Map.entry("smart_routing", "智能路由 / L0–L3"),
            Map.entry("services", "外部服务 / 接线"),
            Map.entry("asset_paths", "资产路径（skill/rule/identity · 仓内默认/自定义）"),
            Map.entry("composition", "L3 装配（audit/notifier 实现选择）"),
            Map.entry("harness", "Harness / 规则路径"),
            Map.entry("browser_hosts", "浏览器 Host 白名单"),
            Map.entry("auth", "API 鉴权 / 无 Token 写白名单"));

    /** python patch 需结构化特化的段（java 第一版不支持 patch，读取走通用）。 */
    public static final List<String> PATCH_UNSUPPORTED = List.of(
            "agents", "launch_ports", "asset_paths", "mailbus_device_bridge");

    /** python ENV_SPECS 对等（26 键；secret 不回值；file=store 写 store/.env）。 */
    public record EnvSpec(String key, String label, String group, boolean secret,
                          String placeholder, String file) {
    }

    public static final List<EnvSpec> ENV_SPECS = List.of(
            new EnvSpec("MAILBUS_OLLAMA_BASE_URL", "Ollama 地址（宿主覆盖；Docker 以 services.docker 为准）", "llm", false, "http://127.0.0.1:11434", null),
            new EnvSpec("MAILBUS_OLLAMA_MODEL", "Ollama 模型", "llm", false, "qwen2.5:3b-instruct-q4_K_M", null),
            new EnvSpec("AGENTMEMORY_URL", "AgentMemory 地址（宿主覆盖；Docker 以 services.docker 为准）", "llm", false, "http://127.0.0.1:3111", null),
            new EnvSpec("MAILBUS_INTERNAL_LLM_PROVIDER_PRIORITY", "Provider 优先级", "llm", false, "local,remote", null),
            new EnvSpec("MAILBUS_INTERNAL_LLM_API_KEY", "Remote LLM API Key", "llm", true, null, null),
            new EnvSpec("DEEPSEEK_API_KEY", "DeepSeek API Key", "llm", true, null, null),
            new EnvSpec("OPENAI_API_KEY", "OpenAI API Key", "llm", true, null, null),
            new EnvSpec("N8N_PUBLISH_WEBHOOK_URL", "n8n 发布 Webhook", "n8n", false, "http://127.0.0.1:5678/webhook/mailbus-multi-publish", null),
            new EnvSpec("N8N_PUBLISH_WEBHOOK_SECRET", "n8n Webhook Secret", "n8n", true, null, null),
            new EnvSpec("N8N_BASE_URL", "n8n Base URL", "n8n", false, "http://127.0.0.1:5678", null),
            new EnvSpec("COMFYUI_BASE_URL", "ComfyUI 地址", "comfyui", false, "http://127.0.0.1:8188", null),
            new EnvSpec("COMFYUI_CHECKPOINT", "ComfyUI Checkpoint", "comfyui", false, null, null),
            new EnvSpec("IMAGE_GENERATE_WEBHOOK_URL", "生图 Webhook（可选）", "n8n", false, null, null),
            new EnvSpec("CLINE_PROVIDER", "Cline Provider", "agents", false, null, "store"),
            new EnvSpec("CLINE_MODEL", "Cline Model", "agents", false, null, "store"),
            new EnvSpec("MAILBUS_API_TOKEN", "Mailbus API Token", "security", true, null, null),
            new EnvSpec("OPENCLAW_GATEWAY_TOKEN", "OpenClaw Gateway Token", "gateway", true, null, null),
            new EnvSpec("MAILBUS_SKILLS_ROOT", "技能根（默认=仓内 skills/ example；自定义=设置页绝对路径）", "asset_paths", false, "E:\\path\\to\\custom\\skills", null),
            new EnvSpec("MAILBUS_RULES_ROOT", "规则根（默认=仓内 rules/ example；自定义=设置页绝对路径）", "asset_paths", false, "E:\\path\\to\\custom\\rules", null),
            new EnvSpec("MAILBUS_IDENTITIES_ROOT", "身份根（默认=仓内 identities/ example；自定义=设置页绝对路径）", "asset_paths", false, "E:\\path\\to\\custom\\identities", null),
            new EnvSpec("AGENT_VAULT_ROOT", "Agent Vault 根（可选；人物/技能 SoT，设置页填写）", "paths", false, "E:\\path\\to\\Obsidian\\Vaults\\Agent", null),
            new EnvSpec("MEMORY_BRIDGE_AGENTMEMORY", "AgentMemory 桥接（0=SQLite-only 降级，1=完整 AgentMemory）", "memory", false, "1", null));

    private final Path dataDir;
    private final Path mailbusRoot;

    public SettingsAdminService(Path dataDir, Path mailbusRoot) {
        this.dataDir = dataDir;
        this.mailbusRoot = mailbusRoot;
    }

    /** GET sections — python list_sections 对等。 */
    public List<Map<String, Object>> listSections() {
        List<Map<String, Object>> out = new ArrayList<>();
        List<String> sorted = new ArrayList<>(EDITABLE_SECTIONS);
        java.util.Collections.sort(sorted); // python sorted() 对等
        for (String sid : sorted) {
            out.add(Map.of("id", sid, "label", SECTION_LABELS.getOrDefault(sid, sid), "editable", true));
        }
        return out;
    }

    /** GET section — 白名单校验 + 通用形状；scheduler/device_bridge 小特化对等。 */
    public Map<String, Object> getSection(String section) {
        if (!EDITABLE_SECTIONS.contains(section)) {
            throw new IllegalArgumentException("unknown section: " + section);
        }
        Map<String, Object> cfg = readConfig();
        if ("scheduler".equals(section)) {
            Map<String, Object> sched = asMap(cfg.get("scheduler"));
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("enabled", sched.getOrDefault("enabled", true));
            data.put("tick_seconds", sched.getOrDefault("tick_seconds", 10));
            data.put("jobs", sched.getOrDefault("jobs", List.of()));
            return Map.of("section", section, "data", data);
        }
        // 通用形状：{section, data: cfg[section] or {}}（python 大特化段的第一版偏差）
        return Map.of("section", section, "data", asMap(cfg.get(section)));
    }

    /** POST section — 通用深合并 + auth/browser_hosts/services 特化；不支持段显式 400。 */
    public Map<String, Object> patchSection(String section, Map<String, Object> patch) {
        if (!EDITABLE_SECTIONS.contains(section)) {
            throw new IllegalArgumentException("unknown section: " + section);
        }
        if (PATCH_UNSUPPORTED.contains(section)) {
            throw new UnsupportedOperationException(
                    "section not supported in java yet: " + section);
        }
        Path configPath = dataDir.resolve("config.json");
        Map<String, Object> cfg = readConfig();
        List<String> requiresRestart = new ArrayList<>();

        if ("auth".equals(section)) {
            patchAuth(cfg, patch);
            requiresRestart.add("auth");
        } else if ("browser_hosts".equals(section)) {
            Object hosts = patch.get("browser_hosts");
            if (hosts instanceof List<?> l) {
                List<String> cleaned = new ArrayList<>();
                for (Object h : l) {
                    String s = String.valueOf(h).trim();
                    if (!s.isEmpty()) {
                        cleaned.add(s);
                    }
                }
                cfg.put("browser_hosts", cleaned);
            }
            requiresRestart.add("browser_hosts");
        } else {
            // 通用深合并（python 兜底分支；services 同为深合并形状）
            Map<String, Object> current = asMap(cfg.get(section));
            cfg.put(section, deepMerge(current, patch));
            if (List.of("scheduler", "mailbus_internal_llm", "mailbus_intake_bridge",
                    "smart_routing", "services").contains(section)) {
                requiresRestart.add(section);
            }
        }
        JsonFiles.write(configPath, cfg);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("section", section);
        out.put("requires_restart", requiresRestart);
        out.put("warnings", List.of());
        out.put("effects", List.of());
        if ("auth".equals(section)) {
            out.put("data", asMap(cfg.get("auth")));
        }
        return out;
    }

    /** python auth patch 对等：allow_write_without_token 布尔 + 三 CIDR 列表键 + 过宽网段拒绝。 */
    private static void patchAuth(Map<String, Object> cfg, Map<String, Object> patch) {
        Map<String, Object> body = patch.get("data") instanceof Map<?, ?> d ? asMap(d) : patch;
        Map<String, Object> next = new LinkedHashMap<>(asMap(cfg.get("auth")));
        if (body.containsKey("allow_write_without_token")) {
            next.put("allow_write_without_token", Boolean.valueOf(String.valueOf(body.get("allow_write_without_token"))));
        }
        for (String ck : List.of("write_without_token_cidrs", "exempt_cidrs", "cors_origins")) {
            if (!body.containsKey(ck)) {
                continue;
            }
            Object raw = body.get(ck);
            List<String> list = new ArrayList<>();
            if (raw instanceof String s) {
                for (String x : s.replace(";", "\n").split("\n")) {
                    if (!x.trim().isEmpty()) {
                        list.add(x.trim());
                    }
                }
            } else if (raw instanceof List<?> l) {
                for (Object x : l) {
                    if (!String.valueOf(x).trim().isEmpty()) {
                        list.add(String.valueOf(x).trim());
                    }
                }
            } else {
                throw new IllegalArgumentException(ck + " must be list or multiline string");
            }
            if (!ck.equals("cors_origins") && (list.contains("0.0.0.0/0") || list.contains("::/0"))) {
                throw new IllegalArgumentException("拒绝过宽网段 0.0.0.0/0 或 ::/0");
            }
            next.put(ck, list);
        }
        cfg.put("auth", next);
    }

    /** GET env — python env_status 对等（分组 + secret 不回值）。 */
    public Map<String, Object> envStatus() {
        loadMailbusEnv();
        Map<String, List<Map<String, Object>>> groups = new LinkedHashMap<>();
        for (EnvSpec spec : ENV_SPECS) {
            String val = System.getenv(spec.key()) == null ? "" : System.getenv(spec.key());
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("key", spec.key());
            entry.put("label", spec.label());
            entry.put("group", spec.group());
            entry.put("secret", spec.secret());
            entry.put("configured", !val.isEmpty());
            entry.put("value", spec.secret() ? null : val);
            entry.put("placeholder", spec.placeholder() == null ? "" : spec.placeholder());
            entry.put("file_hint", spec.file() == null ? "project .env" : spec.file());
            groups.computeIfAbsent(spec.group(), k -> new ArrayList<>()).add(entry);
        }
        return Map.of("groups", groups);
    }

    /** POST env — 白名单键写 .env（project 或 store；updated/skipped/requires_restart）。 */
    public Map<String, Object> patchEnv(Map<String, Object> varsPatch) {
        Path primary = mailbusRoot.resolve(".env");
        try {
            if (!Files.isRegularFile(primary)) {
                Files.createDirectories(primary.getParent());
                Files.writeString(primary, "", StandardCharsets.UTF_8);
            }
        } catch (IOException e) {
            throw new IllegalStateException("cannot init .env: " + e.getMessage());
        }
        List<String> updated = new ArrayList<>();
        List<String> skipped = new ArrayList<>();
        for (Map.Entry<String, Object> e : varsPatch.entrySet()) {
            EnvSpec spec = ENV_SPECS.stream().filter(s -> s.key().equals(e.getKey())).findFirst().orElse(null);
            if (spec == null) {
                skipped.add(e.getKey());
                continue;
            }
            String val = e.getValue() == null ? "" : String.valueOf(e.getValue());
            if (val.isEmpty() || val.equals("***")) {
                continue;
            }
            Path target = "store".equals(spec.file()) ? dataDir.resolve(".env") : primary;
            setEnvKey(target, e.getKey(), val);
            updated.add(e.getKey());
        }
        return Map.of("updated", updated, "skipped", skipped, "requires_restart", List.of("env"));
    }

    /** python _set_env_key 对等：key=value 行替换或追加。 */
    static void setEnvKey(Path path, String key, String value) {
        List<String> lines = new ArrayList<>();
        if (Files.isRegularFile(path)) {
            try {
                lines = new ArrayList<>(Files.readAllLines(path, StandardCharsets.UTF_8));
            } catch (IOException ignored) {
                // 读失败按空文件处理
            }
        }
        String pair = key + "=" + value;
        boolean replaced = false;
        for (int i = 0; i < lines.size(); i++) {
            String l = lines.get(i);
            if (l.startsWith(key + "=") || (l.startsWith("#") && l.contains(key + "=") && false)) {
                lines.set(i, pair);
                replaced = true;
                break;
            }
        }
        if (!replaced) {
            lines.add(pair);
        }
        try {
            Files.write(path, lines, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("cannot write .env: " + e.getMessage());
        }
    }

    /** .env 载入进程环境（python load_mailbus_env 最小对等：不覆盖已有）。 */
    void loadMailbusEnv() {
        for (Path p : List.of(mailbusRoot.resolve(".env"), dataDir.resolve(".env"))) {
            if (!Files.isRegularFile(p)) {
                continue;
            }
            try {
                for (String line : Files.readAllLines(p, StandardCharsets.UTF_8)) {
                    String t = line.trim();
                    if (t.isEmpty() || t.startsWith("#") || !t.contains("=")) {
                        continue;
                    }
                    int eq = t.indexOf('=');
                    if (System.getenv(t.substring(0, eq)) == null
                            && System.getProperty(t.substring(0, eq)) == null) {
                        // JVM 进程环境不可变；记录在 system properties 供 envStatus 一致性
                        System.setProperty(t.substring(0, eq), t.substring(eq + 1));
                    }
                }
            } catch (IOException ignored) {
                // 单文件读失败跳过
            }
        }
    }

    /** GET compose-files — docker-compose*.yml 列表（python list_compose_files 对等）。 */
    public List<Map<String, Object>> listComposeFiles() {
        List<Map<String, Object>> items = new ArrayList<>();
        java.util.Set<String> seen = new java.util.HashSet<>();
        // python compose_roots：root/docker-agents 优先，再 root 本身
        for (Path base : List.of(mailbusRoot.resolve("docker-agents"), mailbusRoot)) {
            if (!Files.isDirectory(base)) {
                continue;
            }
            List<Path> files = new ArrayList<>();
            try (var s = Files.list(base)) {
                s.filter(f -> {
                    String n = f.getFileName().toString();
                    return n.startsWith("docker-compose") && (n.endsWith(".yml") || n.endsWith(".yaml"));
                }).forEach(files::add);
            } catch (IOException ignored) {
                continue;
            }
            files.sort(Path::compareTo);
            for (Path f : files) {
                // 相对 mailbusRoot 的路径（docker-agents/xxx.yml 或 xxx.yml）
                String rel;
                if (base.equals(mailbusRoot)) {
                    rel = f.getFileName().toString();
                } else {
                    rel = base.getFileName().toString() + "/" + f.getFileName().toString();
                }
                final String relKey = rel;
                if (seen.contains(relKey)) {
                    continue;
                }
                seen.add(relKey);
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("path", relKey);
                item.put("name", relKey);
                item.put("file", relKey);
                items.add(item);
            }
        }
        return items;
    }

    private Map<String, Object> readConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        return cfg == null ? new LinkedHashMap<>() : cfg;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) {
        return o instanceof Map<?, ?> m ? new LinkedHashMap<>((Map<String, Object>) m) : new LinkedHashMap<>();
    }

    /** python _deep_merge 对等。 */
    static Map<String, Object> deepMerge(Map<String, Object> base, Map<String, Object> patch) {
        Map<String, Object> out = new LinkedHashMap<>(base);
        for (Map.Entry<String, Object> e : patch.entrySet()) {
            if (e.getValue() instanceof Map<?, ?> v && out.get(e.getKey()) instanceof Map<?, ?> b) {
                out.put(e.getKey(), deepMerge(asMap(b), asMap(v)));
            } else {
                out.put(e.getKey(), e.getValue());
            }
        }
        return out;
    }
}
