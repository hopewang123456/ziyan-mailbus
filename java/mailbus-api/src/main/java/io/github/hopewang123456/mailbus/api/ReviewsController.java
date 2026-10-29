package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.SharedRoots;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.format.DateTimeFormatter;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 审查报告与框架面（批 A6 二组，2026-10-29）— python handlers_system 对等：
 * GET /api/reviews · /api/reviews/projects · /api/reviews/{file} ·
 * GET /api/frameworks（骨架）；frameworks enable/disable 与 agent-instances
 * 四条显式 501（java 无框架发现/多实例机制，登记）。
 */
@RestController
public class ReviewsController {

    private final Path dataDir;

    public ReviewsController(Environment env) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    /** GET /api/reviews — 审查报告列表（reports/*.md 倒序，file/repo/size/time/content 300 字）。 */
    @GetMapping("/api/reviews")
    public Map<String, Object> reviews() {
        List<Map<String, Object>> reports = new ArrayList<>();
        List<Path> files = mdFiles("reports");
        for (int i = files.size() - 1; i >= 0; i--) {
            Path f = files.get(i);
            try {
                String fname = f.getFileName().toString();
                String content = Files.readString(f, StandardCharsets.UTF_8);
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("file", fname);
                item.put("repo", extractRepoName(fname));
                item.put("size", Files.size(f));
                item.put("time", mtime(f, "yyyy-MM-dd HH:mm:ss"));
                item.put("content", content.length() > 300 ? content.substring(0, 300) : content);
                reports.add(item);
            } catch (IOException ignored) {
                // 单文件读失败跳过
            }
        }
        return Map.of("reports", reports, "count", reports.size());
    }

    /** GET /api/reviews/projects — 按仓库分组（每组尾 10 条 file/time/size）。 */
    @GetMapping("/api/reviews/projects")
    public Map<String, Object> reviewProjects() {
        Map<String, List<Map<String, Object>>> projects = new LinkedHashMap<>();
        List<Path> files = mdFiles("reports");
        for (int i = files.size() - 1; i >= 0; i--) {
            Path f = files.get(i);
            try {
                String fname = f.getFileName().toString();
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("file", fname);
                item.put("time", mtime(f, "yyyy-MM-dd HH:mm:ss"));
                item.put("size", Files.size(f));
                projects.computeIfAbsent(extractRepoName(fname), k -> new ArrayList<>()).add(item);
            } catch (IOException ignored) {
                // 单文件读失败跳过
            }
        }
        for (List<Map<String, Object>> v : projects.values()) {
            while (v.size() > 10) {
                v.remove(0);
            }
        }
        return Map.of("projects", projects, "count", projects.size());
    }

    /** GET /api/reviews/{file} — 单份报告（无 markdown 库 → pre 包裹，python ImportError 分支同语义）。 */
    @GetMapping("/api/reviews/{file}")
    public ResponseEntity<Map<String, Object>> reviewDetail(@PathVariable("file") String fname) {
        if (fname == null || !fname.endsWith(".md") || fname.contains("..")
                || !fname.equals(Path.of(fname).getFileName().toString())) {
            return ResponseEntity.status(404).body(Map.of("error", "not found"));
        }
        Path f = dataDir.resolve("reports").resolve(fname);
        if (!Files.isRegularFile(f)) {
            return ResponseEntity.status(404).body(Map.of("error", "not found"));
        }
        try {
            String content = Files.readString(f, StandardCharsets.UTF_8);
            return ResponseEntity.ok(Map.of(
                    "file", fname,
                    "html", "<pre>" + content + "</pre>",
                    "raw", content));
        } catch (IOException e) {
            return ResponseEntity.status(500).body(Map.of("error", String.valueOf(e.getMessage())));
        }
    }

    /** GET /api/frameworks — 框架发现状态（java 无发现机制，空骨架对形状）。 */
    @GetMapping("/api/frameworks")
    public Map<String, Object> frameworks() {
        return Map.of("frameworks", Map.of());
    }

    /** POST /api/frameworks/{id}/enable|disable — 框架启停（java 无机制，501 登记）。 */
    @PostMapping("/api/frameworks/{id}/enable")
    public ResponseEntity<Map<String, Object>> frameworkEnable(@PathVariable("id") String id) {
        return notImplemented("frameworks enable");
    }

    @PostMapping("/api/frameworks/{id}/disable")
    public ResponseEntity<Map<String, Object>> frameworkDisable(@PathVariable("id") String id) {
        return notImplemented("frameworks disable");
    }

    /** POST /api/agent-instances* 四条 — python 多实例机制（java 无，501 登记）。 */
    @PostMapping("/api/agent-instances")
    public ResponseEntity<Map<String, Object>> instanceUpsert() {
        return notImplemented("agent-instances upsert");
    }

    @PostMapping("/api/agent-instances/load-roles")
    public ResponseEntity<Map<String, Object>> instanceLoadRoles() {
        return notImplemented("agent-instances load-roles");
    }

    @PostMapping("/api/agent-instances/discover")
    public ResponseEntity<Map<String, Object>> instanceDiscover() {
        return notImplemented("agent-instances discover");
    }

    @PostMapping("/api/agent-instances/test-connection")
    public ResponseEntity<Map<String, Object>> instanceTestConnection() {
        return notImplemented("agent-instances test-connection");
    }

    private static ResponseEntity<Map<String, Object>> notImplemented(String what) {
        return ResponseEntity.status(501).body(Map.of(
                "status", "error", "error", "not_implemented",
                "detail", "java " + what + " 未对等（批 A6 显式登记）"));
    }

    /** python _extract_repo_name 对等。 */
    static String extractRepoName(String fname) {
        String[] parts = fname.replace(".md", "").split("-");
        if (parts.length >= 3 && parts[0].equals("review")) {
            List<String> repoParts = new ArrayList<>();
            for (String p : parts) {
                if (p == parts[0]) {
                    continue;
                }
                if (p.matches("\\d{8,}")) {
                    break;
                }
                if (p.length() <= 8 && p.toLowerCase().matches("[0-9a-f]+") && !p.isEmpty()) {
                    return "未知项目（旧报告）";
                }
                repoParts.add(p);
            }
            if (!repoParts.isEmpty()) {
                return String.join("-", repoParts);
            }
        }
        return "未知项目（旧报告）";
    }

    private static String mtime(Path f, String pattern) {
        try {
            return DateTimeFormatter.ofPattern(pattern)
                    .withZone(ZoneId.systemDefault())
                    .format(Files.getLastModifiedTime(f).toInstant());
        } catch (IOException ignored) {
            return "";
        }
    }

    private List<Path> mdFiles(String subdir) {
        List<Path> files = new ArrayList<>();
        Path dir = dataDir.resolve(subdir);
        if (!Files.isDirectory(dir)) {
            return files;
        }
        try (var s = Files.list(dir)) {
            s.filter(f -> f.getFileName().toString().endsWith(".md")).sorted().forEach(files::add);
        } catch (IOException ignored) {
            // 目录不可读 → 空
        }
        return files;
    }
}
