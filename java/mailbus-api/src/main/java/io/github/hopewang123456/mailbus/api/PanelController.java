package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 面板读型端点（批 A6 第一组，2026-10-29）— python handlers_system 对等：
 * GET /api/templates · /api/reports · /api/patrol-reports ·
 * /api/workload · /api/tokens/summary。
 */
@RestController
public class PanelController {

    private static final ZoneId CN = ZoneId.of("Asia/Shanghai");

    private final Path dataDir;
    private final TaskRepository tasks;

    public PanelController(Environment env, TaskRepository tasks) {
        this.dataDir = SharedRoots.resolveDataDir(env.getProperty("mailbus.data-dir"));
        this.tasks = tasks;
    }

    /** GET /api/templates — agent 类型模板（config.agent_types 段直读）。 */
    @GetMapping("/api/templates")
    public Map<String, Object> templates() {
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        Object types = cfg == null ? Map.of() : cfg.getOrDefault("agent_types", Map.of());
        return types instanceof Map<?, ?> m ? cast(m) : Map.of();
    }

    /** GET /api/reports — 错误报告（errors/*.jsonl 尾 7 文件，每文件尾 20 行）。 */
    @GetMapping("/api/reports")
    public Map<String, Object> reports() {
        List<Map<String, Object>> reports = new ArrayList<>();
        Path dir = dataDir.resolve("errors");
        List<Path> files = jsonlFiles(dir);
        for (int i = files.size() - 1; i >= 0 && reports.size() < 7; i--) {
            Path f = files.get(i);
            try {
                List<String> lines = Files.readAllLines(f, StandardCharsets.UTF_8);
                List<Map<String, Object>> recent = new ArrayList<>();
                for (int j = Math.max(0, lines.size() - 20); j < lines.size(); j++) {
                    String line = lines.get(j).trim();
                    if (line.isEmpty()) {
                        continue;
                    }
                    try {
                        var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                        recent.add(cast(mapper.readValue(line, Map.class)));
                    } catch (Exception ignored) {
                        // 脏行跳过（python JSONDecodeError 同语义）
                    }
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("file", f.getFileName().toString());
                item.put("count", lines.size());
                item.put("recent", recent);
                reports.add(item);
            } catch (IOException ignored) {
                // 单文件读失败跳过
            }
        }
        return Map.of("reports", reports);
    }

    /** GET /api/patrol-reports — 巡检日报（patrol_reports/*.md 尾 20 元信息）。 */
    @GetMapping("/api/patrol-reports")
    public Map<String, Object> patrolReports() {
        List<Map<String, Object>> reports = new ArrayList<>();
        Path dir = dataDir.resolve("patrol_reports");
        if (!Files.isDirectory(dir)) {
            return Map.of("reports", reports);
        }
        List<Path> files = new ArrayList<>();
        try (var s = Files.list(dir)) {
            s.filter(f -> f.getFileName().toString().endsWith(".md")).sorted().forEach(files::add);
        } catch (IOException ignored) {
            return Map.of("reports", reports);
        }
        for (int i = files.size() - 1; i >= 0 && reports.size() < 20; i--) {
            Path f = files.get(i);
            try {
                String content = Files.readString(f, StandardCharsets.UTF_8);
                String mtime;
                try {
                    // python fromtimestamp 用系统默认时区——对齐（勿固定 +8）
                    mtime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
                            .withZone(ZoneId.systemDefault())
                            .format(Files.getLastModifiedTime(f).toInstant());
                } catch (IOException ignored) {
                    mtime = "";
                }
                String summary = content.length() > 300 ? content.substring(0, 300) : content;
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("file", f.getFileName().toString());
                item.put("date", mtime);
                item.put("created_at", mtime);
                item.put("summary", summary.trim());
                item.put("content", content.length() > 500 ? content.substring(0, 500) : content);
                reports.add(item);
            } catch (IOException ignored) {
                // 单文件读失败跳过
            }
        }
        return Map.of("reports", reports);
    }

    /** GET /api/workload — Agent 负载摘要（活跃任务/排队步骤/收件箱积压）。 */
    @GetMapping("/api/workload")
    public Map<String, Object> workload() {
        Map<String, Integer> activeByAgent = new LinkedHashMap<>();
        Map<String, Integer> queuedByAgent = new LinkedHashMap<>();
        for (Map<String, Object> t : tasks.listAll()) {
            String status = str(t.get("status"));
            if (!status.equals("running") && !status.equals("pending")) {
                continue;
            }
            String assignee = str(t.get("assignee"));
            if (!assignee.isEmpty()) {
                activeByAgent.merge(assignee, 1, Integer::sum);
            }
            for (Object o : t.get("chain") instanceof List<?> l ? l : List.of()) {
                if (!(o instanceof Map<?, ?> s)) {
                    continue;
                }
                String fs = str(s.get("fsm_state"));
                boolean queued = fs.equals("queued") || fs.equals("awaiting_result")
                        || "running".equals(str(s.get("status")));
                if (!queued) {
                    continue;
                }
                String ag = !str(s.get("to_agent")).isEmpty() ? str(s.get("to_agent")) : str(s.get("to_person"));
                if (!ag.isEmpty()) {
                    queuedByAgent.merge(ag, 1, Integer::sum);
                }
            }
        }
        Map<String, Object> agentsOut = new LinkedHashMap<>();
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        Map<String, Object> agents = cfg != null && cfg.get("agents") instanceof Map<?, ?> am ? cast(am) : Map.of();
        for (Map.Entry<String, Object> e : agents.entrySet()) {
            String name = e.getKey();
            Map<String, Object> ac = e.getValue() instanceof Map<?, ?> m ? cast(m) : Map.of();
            long inboxCount = inboxCount(name);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("name", ac.getOrDefault("name", name));
            item.put("role", ac.getOrDefault("role", ""));
            item.put("active_tasks", activeByAgent.getOrDefault(name, 0));
            item.put("queued_steps", queuedByAgent.getOrDefault(name, 0));
            item.put("inbox_pending", inboxCount);
            agentsOut.put(name, item);
        }
        return Map.of(
                "agents", agentsOut,
                "generated_at", OffsetDateTime.now(CN)
                        .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ")));
    }

    /** GET /api/tokens/summary — token 台账今日视图（ledger 分片聚合，python today_summary 对等）。 */
    @GetMapping("/api/tokens/summary")
    public Map<String, Object> tokenSummary() {
        Path day = dataDir.resolve("ledger")
                .resolve("tokens-" + LocalDate.now(CN).format(DateTimeFormatter.ofPattern("yyyy-MM-dd")) + ".jsonl");
        List<Map<String, Object>> entries = new ArrayList<>();
        if (Files.isRegularFile(day)) {
            try {
                var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                for (String line : Files.readAllLines(day, StandardCharsets.UTF_8)) {
                    if (line.trim().isEmpty()) {
                        continue;
                    }
                    try {
                        entries.add(cast(mapper.readValue(line, Map.class)));
                    } catch (Exception ignored) {
                        // 脏行跳过
                    }
                }
            } catch (IOException ignored) {
                // 读失败按空
            }
        }
        int total = 0;
        int calls = 0;
        Map<String, Integer> byAgent = new LinkedHashMap<>();
        Map<String, Integer> byTask = new LinkedHashMap<>();
        Map<String, Integer> byKind = new LinkedHashMap<>();
        Map<String, Integer> byMinute = new LinkedHashMap<>();
        for (Map<String, Object> e : entries) {
            int est = parseIntOr(e.get("est_tokens"), 0);
            total += est;
            calls++;
            byAgent.merge(str(e.get("agent")).isEmpty() ? "?" : str(e.get("agent")), est, Integer::sum);
            byKind.merge(str(e.get("kind")).isEmpty() ? "?" : str(e.get("kind")), est, Integer::sum);
            String t = str(e.get("task_id"));
            if (!t.isEmpty()) {
                byTask.merge(t, est, Integer::sum);
            }
            String minute = str(e.get("ts"));
            minute = minute.length() > 16 ? minute.substring(0, 16) : minute;
            if (!minute.isEmpty()) {
                byMinute.merge(minute, est, Integer::sum);
            }
        }
        String peakMinute = "";
        int peakTokens = 0;
        for (Map.Entry<String, Integer> e : byMinute.entrySet()) {
            if (e.getValue() > peakTokens) {
                peakMinute = e.getKey();
                peakTokens = e.getValue();
            }
        }
        Map<String, Object> cfg = JsonFiles.readMap(dataDir.resolve("config.json"));
        int budget = 0;
        if (cfg != null && cfg.get("mailbus_automation") instanceof Map<?, ?> auto
                && auto.get("token_budget") instanceof Map<?, ?> tb) {
            budget = parseIntOr(tb.get("daily_est_tokens"), 0);
        }
        List<Map<String, Object>> topTasks = byTask.entrySet().stream()
                .sorted((a, b) -> b.getValue() - a.getValue())
                .limit(5)
                .map(en -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("task_id", en.getKey());
                    m.put("est_tokens", en.getValue());
                    return m;
                })
                .toList();
        Map<String, Object> byAgentSorted = new LinkedHashMap<>();
        byAgent.entrySet().stream().sorted((a, b) -> b.getValue() - a.getValue())
                .forEach(en -> byAgentSorted.put(en.getKey(), en.getValue()));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("day", LocalDate.now(CN).format(DateTimeFormatter.ofPattern("yyyy-MM-dd")));
        out.put("calls", calls);
        out.put("est_tokens_total", total);
        out.put("by_kind", byKind);
        out.put("by_agent", byAgentSorted);
        out.put("top_tasks", topTasks);
        out.put("peak", Map.of("minute", peakMinute, "est_tokens", peakTokens));
        Map<String, Object> budgetOut = new LinkedHashMap<>();
        budgetOut.put("daily_est_tokens", budget);
        budgetOut.put("exceeded", budget > 0 && total > budget);
        budgetOut.put("used_pct", budget > 0 ? Math.round(total * 1000.0 / budget) / 10.0 : null);
        out.put("budget", budgetOut);
        return out;
    }

    private long inboxCount(String agent) {
        // java 消息存储（一消息一文件）——按 agent 目录文件数近似（python inbox.json 数组长度）
        Path dir = dataDir.resolve("messages").resolve(agent);
        if (!Files.isDirectory(dir)) {
            return 0;
        }
        try (var s = Files.list(dir)) {
            return s.filter(f -> f.getFileName().toString().endsWith(".json")).count();
        } catch (IOException ignored) {
            return 0;
        }
    }

    private static List<Path> jsonlFiles(Path dir) {
        List<Path> files = new ArrayList<>();
        if (!Files.isDirectory(dir)) {
            return files;
        }
        try (var s = Files.list(dir)) {
            s.filter(f -> f.getFileName().toString().endsWith(".jsonl")).sorted().forEach(files::add);
        } catch (IOException ignored) {
            // 目录不可读 → 空
        }
        return files;
    }

    private static int parseIntOr(Object o, int fallback) {
        return o instanceof Number n ? n.intValue() : fallback;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
