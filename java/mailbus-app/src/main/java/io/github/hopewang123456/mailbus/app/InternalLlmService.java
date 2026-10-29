package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Internal LLM 面板（java 机制深化批二，2026-10-30）— python
 * {@code adapters/internal_llm/probe.py} 对等：
 * provider 探测（ollama /api/tags、openai_compatible /models）+
 * probe_all 聚合（active/fallback_mode/ready）+ rag index_info/chunks 重建。
 *
 * <p>dry-run 走 TaskPlannerService（M2c 已有 Spring AI LlmClient 通道）。
 */
public class InternalLlmService {

    private final Path dataDir;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).build();

    public InternalLlmService(Path dataDir) {
        this.dataDir = dataDir;
    }

    /** python load_llm_config：config.json mailbus_internal_llm 段。 */
    public Map<String, Object> loadConfig() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        return cfg != null && cfg.get("mailbus_internal_llm") instanceof Map<?, ?> m
                ? cast(m) : Map.of();
    }

    /** python probe_provider 分发（stub/ollama/openai_compatible；anthropic 骨架）。 */
    public Map<String, Object> probeProvider(String name, Map<String, Object> pc) {
        String kind = str(pc.get("protocol")).isEmpty()
                ? str(pc.get("kind")).isEmpty() ? name : str(pc.get("kind"))
                : str(pc.get("protocol"));
        kind = kind.toLowerCase();
        if (kind.equals("stub") || name.equals("stub")) {
            return Map.of("ok", true, "kind", "stub", "name", name);
        }
        if (kind.equals("ollama")) {
            Map<String, Object> out = probeOllama(pc);
            out.put("name", name);
            return out;
        }
        if (kind.equals("openai_compatible") || kind.equals("openai")) {
            Map<String, Object> out = probeOpenaiCompatible(pc);
            out.put("name", name);
            return out;
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", false);
        out.put("name", name);
        out.put("kind", kind);
        out.put("error", "unknown kind " + kind);
        return out;
    }

    private Map<String, Object> probeOllama(Map<String, Object> pc) {
        String base = str(pc.get("base_url")).isEmpty() ? "http://127.0.0.1:11434" : str(pc.get("base_url"));
        base = trimSlash(base);
        String model = str(pc.get("model"));
        int timeout = intOr(pc.get("timeout_seconds"), 10);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("kind", "ollama");
        out.put("base_url", base);
        out.put("model", model);
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(base + "/api/tags"))
                    .timeout(Duration.ofSeconds(timeout)).GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var root = mapper.readTree(resp.body());
            List<String> models = new ArrayList<>();
            if (root.get("models") != null) {
                for (var m : root.get("models")) {
                    if (m.get("name") != null && !m.get("name").isNull()) {
                        models.add(m.get("name").asText());
                    }
                }
            }
            boolean hasModel = model.isEmpty()
                    || models.stream().anyMatch(m -> m.contains(model));
            out.put("ok", true);
            out.put("model_available", hasModel);
            out.put("models_count", models.size());
        } catch (Exception e) {
            out.put("ok", false);
            out.put("error", String.valueOf(e.getMessage()));
        }
        return out;
    }

    private Map<String, Object> probeOpenaiCompatible(Map<String, Object> pc) {
        String base = trimSlash(str(pc.get("base_url")));
        String envKey = str(pc.get("api_key_env")).isEmpty()
                ? "MAILBUS_INTERNAL_LLM_API_KEY" : str(pc.get("api_key_env"));
        String apiKey = System.getenv(envKey);
        if (apiKey == null || apiKey.isBlank()) {
            apiKey = str(pc.get("api_key"));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("kind", "openai_compatible");
        if (base.isEmpty()) {
            out.put("ok", false);
            out.put("error", "missing base_url");
            return out;
        }
        out.put("base_url", base);
        if (apiKey.isEmpty()) {
            out.put("ok", false);
            out.put("error", "missing env " + envKey);
            return out;
        }
        int timeout = intOr(pc.get("timeout_seconds"), 10);
        String model = str(pc.get("model"));
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(base + "/models"))
                    .header("Authorization", "Bearer " + apiKey)
                    .timeout(Duration.ofSeconds(timeout)).GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var root = mapper.readTree(resp.body());
            List<String> models = new ArrayList<>();
            if (root.get("data") != null) {
                for (var m : root.get("data")) {
                    if (m.get("id") != null && !m.get("id").isNull()) {
                        models.add(m.get("id").asText());
                    }
                }
            }
            boolean hasModel = model.isEmpty()
                    || models.stream().anyMatch(m -> m.contains(model));
            out.put("ok", true);
            out.put("model_available", hasModel);
            out.put("models_count", models.size());
        } catch (Exception e) {
            out.put("ok", false);
            out.put("error", String.valueOf(e.getMessage()));
        }
        return out;
    }

    /** python probe_all 聚合。 */
    public Map<String, Object> probeAll() {
        Map<String, Object> cfg = loadConfig();
        Map<String, Object> providers = cfg.get("providers") instanceof Map<?, ?> pm ? cast(pm) : Map.of();
        List<String> order = new ArrayList<>();
        if (cfg.get("provider_priority") instanceof List<?> l) {
            for (Object o : l) {
                order.add(String.valueOf(o));
            }
        }
        List<Map<String, Object>> results = new ArrayList<>();
        String active = null;
        for (String name : order) {
            if (!providers.containsKey(name)) {
                continue;
            }
            Map<String, Object> r = probeProvider(name, cast((Map<?, ?>) providers.get(name)));
            results.add(r);
            boolean modelAvailable = !r.containsKey("model_available")
                    || Boolean.TRUE.equals(r.get("model_available"));
            if (active == null && Boolean.TRUE.equals(r.get("ok")) && modelAvailable) {
                active = name;
            }
        }
        Map<String, Object> rag = ragInfo(cfg);
        Map<String, Object> out = new LinkedHashMap<>();
        boolean enabled = Boolean.TRUE.equals(cfg.get("enabled"));
        out.put("enabled", enabled);
        out.put("active_provider", active);
        out.put("provider_priority", order);
        out.put("fallback_mode", !order.isEmpty() && "local".equals(order.get(0)) ? "local_first" : "custom");
        out.put("providers", results);
        out.put("rag", rag);
        out.put("ready", enabled && active != null);
        return out;
    }

    /** python index_info：chunks 计数。 */
    public Map<String, Object> ragInfo(Map<String, Object> cfg) {
        Map<String, Object> ragCfg = cfg.get("rag") instanceof Map<?, ?> r ? cast(r) : Map.of();
        if (!Boolean.TRUE.equals(ragCfg.getOrDefault("enabled", true))) {
            return Map.of("enabled", false);
        }
        // python _root_and_index_path：rag.index.path 缺省 store/rag/mailbus-planner.chunks.json
        String rel = str(ragCfg.get("path"));
        // rag 段的 path 在 index 下
        String idxRel = ragCfg.get("index") instanceof Map<?, ?> im ? str(((Map<?, ?>) im).get("path")) : "";
        String relPath = idxRel.isEmpty() ? "store/rag/mailbus-planner.chunks.json" : idxRel;
        if (relPath.endsWith(".sqlite")) {
            relPath = relPath.substring(0, relPath.length() - ".sqlite".length()) + ".chunks.json";
        }
        Path mailRoot = dataDir.getParent() != null ? dataDir.getParent() : dataDir;
        Path index = relPath.startsWith("store/")
                ? mailRoot.resolve(relPath)
                : dataDir.resolve(relPath);
        int chunks = countChunks(index);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("chunks", chunks);
        out.put("enabled", true);
        out.put("path", index.toString());
        return out;
    }

    /** python rebuild_index（简化同构：glob 源→800 字符分块→chunks.json）。 */
    public int rebuildIndex() {
        Map<String, Object> cfg = loadConfig();
        Map<String, Object> ragCfg = cfg.get("rag") instanceof Map<?, ?> r ? cast(r) : Map.of();
        int maxChars = intOr(ragCfg.get("max_chars_per_chunk"), 800);
        Path mailRoot = dataDir.getParent() != null ? dataDir.getParent() : dataDir;
        List<Map<String, Object>> chunks = new ArrayList<>();
        if (ragCfg.get("sources") instanceof List<?> sources) {
            for (Object o : sources) {
                if (!(o instanceof Map<?, ?> src)) {
                    continue;
                }
                String sid = str(src.get("id")).isEmpty() ? "src" : str(src.get("id"));
                String raw = str(src.get("path")).replace("\\", "/");
                if (raw.isEmpty()) {
                    continue;
                }
                Path dir;
                if (raw.startsWith("store/")) {
                    dir = mailRoot.resolve(raw);
                } else if (Path.of(raw).isAbsolute()) {
                    dir = Path.of(raw);
                } else {
                    dir = mailRoot.resolve(raw);
                }
                String glob = str(src.get("glob")).isEmpty() ? "**/*.md" : str(src.get("glob"));
                int priority = intOr(src.get("priority"), 50);
                List<Path> files = new ArrayList<>();
                if (Files.isDirectory(dir)) {
                    String ext = glob.endsWith("*.md") ? ".md" : ".json";
                    try (var walk = Files.walk(dir)) {
                        walk.filter(Files::isRegularFile)
                                .filter(f -> f.getFileName().toString().endsWith(ext))
                                .forEach(files::add);
                    } catch (IOException ignored) {
                        // 源不可读跳过
                    }
                }
                files.sort(Path::compareTo);
                for (Path f : files) {
                    String text;
                    try {
                        text = Files.readString(f);
                    } catch (IOException ignored) {
                        continue;
                    }
                    String title = mailRoot.relativize(f).toString().replace("\\", "/");
                    for (int i = 0; i < text.length(); i += maxChars) {
                        String chunkText = text.substring(i, Math.min(text.length(), i + maxChars));
                        Map<String, Object> c = new LinkedHashMap<>();
                        c.put("source", sid);
                        c.put("title", title);
                        c.put("text", chunkText);
                        c.put("priority", priority);
                        chunks.add(c);
                    }
                }
            }
        }
        // 写 chunks.json（路径解析与 ragInfo 同构）
        Map<String, Object> ragCfg2 = cfg.get("rag") instanceof Map<?, ?> r ? new LinkedHashMap<>(cast(r)) : new LinkedHashMap<>();
        String idxRel = ragCfg2.get("index") instanceof Map<?, ?> im ? str(((Map<?, ?>) im).get("path")) : "";
        String relPath = idxRel.isEmpty() ? "store/rag/mailbus-planner.chunks.json" : idxRel;
        if (relPath.endsWith(".sqlite")) {
            relPath = relPath.substring(0, relPath.length() - ".sqlite".length()) + ".chunks.json";
        }
        Path index = relPath.startsWith("store/") ? mailRoot.resolve(relPath) : dataDir.resolve(relPath);
        try {
            Files.createDirectories(index.getParent());
        } catch (IOException ignored) {
            // dir exists
        }
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("chunks", chunks);
        JsonFiles.write(index, doc);
        return chunks.size();
    }

    private static int countChunks(Path index) {
        Map<String, Object> doc = JsonFiles.readMap(index);
        if (doc != null && doc.get("chunks") instanceof List<?> l) {
            return l.size();
        }
        return 0;
    }

    private static String trimSlash(String s) {
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        return s;
    }

    private static int intOr(Object o, int fallback) {
        return o instanceof Number n ? n.intValue() : fallback;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o).trim();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
