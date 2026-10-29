package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * 任务审计与更新（批 A2，2026-10-29）— python
 * {@code handlers_tasks.handle_task_audit_stats / handle_task_audit_trend /
 * handle_task_audit_pending / handle_task_update} 对等：
 * GET /api/tasks/audit/stats · /api/tasks/audit/stats/trend ·
 * /api/tasks/audit/pending · POST /api/tasks/update。
 */
@RestController
@SuppressWarnings("unchecked")
public class TaskAuditController {

    private final TaskRepository tasks;

    public TaskAuditController(Environment env, TaskRepository tasks) {
        this.tasks = tasks;
    }

    /** GET /api/tasks/audit/stats — 审计聚合统计。 */
    @GetMapping("/api/tasks/audit/stats")
    public Map<String, Object> auditStats() {
        List<Map<String, Object>> all = tasks.listAll();
        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("total_tasks", all.size());
        stats.put("audited_tasks", 0);
        stats.put("pending_audit_tasks", 0);
        stats.put("pass_count", 0);
        stats.put("fail_count", 0);
        stats.put("warn_count", 0);
        Map<String, Object> byReviewer = new LinkedHashMap<>();
        Map<String, Object> byCategory = new LinkedHashMap<>();
        Map<String, Object> bySeverity = new LinkedHashMap<>();
        List<Map<String, Object>> latest = new ArrayList<>();

        for (Map<String, Object> task : all) {
            List<?> auditLog = task.get("audit_log") instanceof List<?> l ? l : List.of();
            if (!auditLog.isEmpty()) {
                stats.put("audited_tasks", ((Number) stats.get("audited_tasks")).intValue() + 1);
                for (Object o : auditLog) {
                    if (!(o instanceof Map<?, ?> em)) {
                        continue;
                    }
                    @SuppressWarnings("unchecked")
                    Map<String, Object> entry = (Map<String, Object>) em;
                    String result = str(entry.get("result"));
                    if (result.equals("pass")) {
                        stats.put("pass_count", ((Number) stats.get("pass_count")).intValue() + 1);
                    } else if (result.equals("fail")) {
                        stats.put("fail_count", ((Number) stats.get("fail_count")).intValue() + 1);
                    } else if (result.equals("warn")) {
                        stats.put("warn_count", ((Number) stats.get("warn_count")).intValue() + 1);
                    }
                    String reviewer = entry.get("reviewer") == null ? "unknown" : str(entry.get("reviewer"));
                    Map<String, Object> rv = byReviewer.get(reviewer) instanceof Map<?, ?> existing
                            ? castMap(existing)
                            : newReviewerRow();
                    byReviewer.put(reviewer, rv);
                    rv.put(result, ((Number) rv.getOrDefault(result, 0)).intValue() + 1);
                    rv.put("total", ((Number) rv.get("total")).intValue() + 1);

                    String cat = entry.get("category") == null || str(entry.get("category")).isEmpty()
                            ? "other" : str(entry.get("category"));
                    byCategory.put(cat, ((Number) byCategory.getOrDefault(cat, 0)).intValue() + 1);

                    String sev = entry.get("severity") == null ? "normal" : str(entry.get("severity"));
                    bySeverity.put(sev, ((Number) bySeverity.getOrDefault(sev, 0)).intValue() + 1);

                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("task_id", task.get("task_id") == null ? "" : task.get("task_id"));
                    String summary = task.get("summary") == null ? "" : str(task.get("summary"));
                    item.put("summary", summary.length() > 60 ? summary.substring(0, 60) : summary);
                    item.put("result", result);
                    item.put("reviewer", reviewer);
                    item.put("at", entry.get("at") == null ? "" : entry.get("at"));
                    latest.add(item);
                }
            } else {
                String status = task.get("status") == null ? "" : str(task.get("status")).toLowerCase();
                if ((status.equals("success") || status.equals("failed") || status.equals("timeout"))
                        && requiresAudit(task)) {
                    stats.put("pending_audit_tasks", ((Number) stats.get("pending_audit_tasks")).intValue() + 1);
                }
            }
        }
        latest.sort(Comparator.comparing((Map<String, Object> x) -> str(x.get("at"))).reversed());
        stats.put("by_reviewer", byReviewer);
        stats.put("by_category", byCategory);
        stats.put("by_severity", bySeverity);
        stats.put("latest_audits", latest.size() > 20 ? latest.subList(0, 20) : latest);

        int totalAudits = ((Number) stats.get("pass_count")).intValue()
                + ((Number) stats.get("fail_count")).intValue()
                + ((Number) stats.get("warn_count")).intValue();
        stats.put("pass_rate", totalAudits > 0
                ? round1(((Number) stats.get("pass_count")).intValue() * 100.0 / totalAudits) : 0.0);
        stats.put("total_audit_entries", totalAudits);
        return stats;
    }

    /** GET /api/tasks/audit/stats/trend — 审计趋势（period=day/week/month, days 回溯窗）。 */
    @GetMapping("/api/tasks/audit/stats/trend")
    public Map<String, Object> auditTrend(
            @RequestParam(defaultValue = "day") String period,
            @RequestParam(defaultValue = "30") int days) {
        List<Map<String, Object>> all = tasks.listAll();
        Map<String, int[]> agg = new TreeMap<>(); // periodKey → [total, pass, fail, warn]
        for (Map<String, Object> task : all) {
            List<?> auditLog = task.get("audit_log") instanceof List<?> l ? l : List.of();
            for (Object o : auditLog) {
                if (!(o instanceof Map<?, ?> em)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> entry = (Map<String, Object>) em;
                String at = str(entry.get("at"));
                if (at.isEmpty()) {
                    continue;
                }
                String key = truncateToPeriod(at, period);
                if (key.isEmpty()) {
                    continue;
                }
                int[] arr = agg.computeIfAbsent(key, k -> new int[4]);
                arr[0]++;
                String result = str(entry.get("result"));
                if (result.equals("pass")) {
                    arr[1]++;
                } else if (result.equals("fail")) {
                    arr[2]++;
                } else if (result.equals("warn")) {
                    arr[3]++;
                }
            }
        }
        if (agg.isEmpty()) {
            Map<String, Object> summary = new LinkedHashMap<>();
            summary.put("total_audits", 0);
            summary.put("avg_pass_rate", 0.0);
            summary.put("period", period);
            summary.put("days", days);
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("trend", List.of());
            out.put("summary", summary);
            return out;
        }
        List<Map<String, Object>> trend = new ArrayList<>();
        int totalAll = 0;
        int totalPass = 0;
        for (Map.Entry<String, int[]> e : agg.entrySet()) {
            int[] a = e.getValue();
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("period", e.getKey());
            row.put("total", a[0]);
            row.put("pass", a[1]);
            row.put("fail", a[2]);
            row.put("warn", a[3]);
            row.put("pass_rate", a[0] > 0 ? round1(a[1] * 100.0 / a[0]) : 0.0);
            trend.add(row);
            totalAll += a[0];
            totalPass += a[1];
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("total_audits", totalAll);
        summary.put("avg_pass_rate", totalAll > 0 ? round1(totalPass * 100.0 / totalAll) : 0.0);
        summary.put("period", period);
        summary.put("days", days);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("trend", trend);
        out.put("summary", summary);
        return out;
    }

    /** GET /api/tasks/audit/pending — 待审计任务列表（limit 默认 50，python list_pending_audit 对等）。 */
    @GetMapping("/api/tasks/audit/pending")
    public Map<String, Object> auditPending(@RequestParam(defaultValue = "50") int limit) {
        List<Map<String, Object>> pending = new ArrayList<>();
        for (Map<String, Object> task : tasks.listAll()) {
            String status = task.get("status") == null ? "" : str(task.get("status"));
            List<?> auditLog = task.get("audit_log") instanceof List<?> l ? l : List.of();
            if (!(status.equals("success") || status.equals("failed") || status.equals("timeout"))) {
                continue;
            }
            if (!auditLog.isEmpty()) {
                continue;
            }
            if (requiresAudit(task)) {
                pending.add(task);
            }
        }
        pending.sort(Comparator
                .comparing((Map<String, Object> t) -> str(t.get("updated_at")))
                .reversed());
        if (pending.size() > limit) {
            pending = pending.subList(0, limit);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("tasks", pending);
        out.put("count", pending.size());
        out.put("limit", limit);
        return out;
    }

    /** POST /api/tasks/update — 更新任务状态（task_id 必填，status 需合法）。 */
    @PostMapping("/api/tasks/update")
    public ResponseEntity<Map<String, Object>> update(@RequestBody Map<String, Object> body) {
        String taskId = str(body.get("task_id"));
        String status = str(body.get("status"));
        if (taskId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "缺少 task_id"));
        }
        if (!ALLOWED_STATUSES.contains(status)) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "无效状态 " + status + "，可选: " + String.join(", ", ALLOWED_STATUSES)));
        }
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            return ResponseEntity.status(404).body(Map.of("error", "task_not_found"));
        }
        Map<String, Object> task = new LinkedHashMap<>(found.get());
        task.put("status", status);
        if (body.containsKey("error")) {
            task.put("error", body.get("error"));
        }
        tasks.save(taskId, task);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("task_id", taskId);
        out.put("task", task);
        return ResponseEntity.ok(out);
    }


    private static Map<String, Object> newReviewerRow() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("pass", 0);
        m.put("fail", 0);
        m.put("warn", 0);
        m.put("total", 0);
        return m;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castMap(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    /** python audit_dispatch.task_requires_audit 对等（显式标记 → 前缀白名单 → 噪声 → chain 判定）。 */
    private static boolean requiresAudit(Map<String, Object> task) {
        Object explicit = task.get("requires_audit");
        if (Boolean.FALSE.equals(explicit)) {
            return false;
        }
        if (Boolean.TRUE.equals(explicit)) {
            return true;
        }
        String tid = task.get("task_id") == null ? "" : str(task.get("task_id"));
        for (String p : NO_AUDIT_PREFIXES) {
            if (tid.startsWith(p)) {
                return false;
            }
        }
        if (isNoiseTask(tid, task.get("summary") == null ? "" : str(task.get("summary")))) {
            return false;
        }
        List<?> chain = task.get("chain") instanceof List<?> l ? l : List.of();
        if (chain.isEmpty() || !(chain.get(0) instanceof Map<?, ?>)) {
            return false;
        }
        Map<?, ?> first = (Map<?, ?>) chain.get(0);
        boolean pipelineStep = first.get("step_id") != null && !str(first.get("step_id")).isEmpty()
                || first.get("to_agent") != null && !str(first.get("to_agent")).isEmpty()
                || first.get("to_person") != null && !str(first.get("to_person")).isEmpty();
        boolean planned = first.get("planned_agents") instanceof List<?> pa && !pa.isEmpty();
        return pipelineStep || planned;
    }

    /** python _is_noise_task 对等：超时/催办前缀 + 提醒类摘要。 */
    private static boolean isNoiseTask(String taskId, String summary) {
        for (String p : SKIP_TIMEOUT_PREFIXES) {
            if (taskId.startsWith(p)) {
                return true;
            }
        }
        String s = summary.length() > 80 ? summary.substring(0, 80) : summary;
        return s.startsWith("⚠️ 超时提醒") || s.startsWith("⏰ 催办提醒");
    }

    /** python tracker.SKIP_TIMEOUT_PREFIXES 对等。 */
    private static final List<String> SKIP_TIMEOUT_PREFIXES = List.of(
            "remind-", "tracker-remind-", "patrol-", "heartbeat-",
            "confirm-", "rule-change-", "alert-task-");

    /** python audit_dispatch.NO_AUDIT_PREFIXES 对等。 */
    private static final List<String> NO_AUDIT_PREFIXES = List.of(
            "msg-", "game-lvup-", "smoke-", "demo-", "test-", "pipeline-",
            "remind-", "tracker-remind-", "patrol-", "heartbeat-",
            "confirm-", "rule-change-", "alert-task-");

    /** ISO 时间截断到周期（day/week/month），python _truncate_to_period 对等。 */
    static String truncateToPeriod(String isoStr, String period) {
        if (isoStr == null || isoStr.isEmpty()) {
            return "";
        }
        String datePart = isoStr.length() > 10 ? isoStr.substring(0, 10) : isoStr;
        if (period.equals("day")) {
            return datePart;
        }
        try {
            LocalDate d = LocalDate.parse(datePart, DateTimeFormatter.ofPattern("yyyy-MM-dd"));
            if (period.equals("week")) {
                java.time.temporal.WeekFields wf = java.time.temporal.WeekFields.ISO;
                return d.get(wf.weekBasedYear())
                        + "-W" + String.format("%02d", d.get(wf.weekOfWeekBasedYear()));
            }
            if (period.equals("month")) {
                return datePart.substring(0, 7);
            }
        } catch (RuntimeException ignored) {
            // 非法日期 → 退回 date part（python 同语义）
        }
        return datePart;
    }

    /** python tracker.TaskStatus.ALL 对等（7 态）。 */
    private static final List<String> ALLOWED_STATUSES =
            List.of("pending", "running", "paused", "success", "failed", "timeout", "cancelled");

    private static double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
