package io.github.hopewang123456.mailbus.audit;

import io.github.hopewang123456.mailbus.metrics.MetricDtos;
import io.github.hopewang123456.mailbus.metrics.MetricsService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AuditService {

    private static final String AUDITED =
            "('approved', 'rejected', 'expired', 'acknowledged')";

    private final JdbcTemplate jdbc;
    private final MetricsService metrics;

    public AuditService(JdbcTemplate jdbc, MetricsService metrics) {
        this.jdbc = jdbc;
        this.metrics = metrics;
    }

    public MetricDtos.AuditStatsOut stats() {
        int totalTasks = count("SELECT COUNT(*) FROM task_tasks");
        int auditedTasks = count("SELECT COUNT(DISTINCT task_id) FROM approval_items"
                + " WHERE status IN " + AUDITED);
        int pendingTasks = count("SELECT COUNT(DISTINCT task_id) FROM approval_items"
                + " WHERE status = 'pending'");
        int passCount = count("SELECT COUNT(*) FROM approval_items"
                + " WHERE status IN ('approved', 'acknowledged')");
        int failCount = count("SELECT COUNT(*) FROM approval_items WHERE status = 'rejected'");
        int warnCount = count("SELECT COUNT(*) FROM approval_items WHERE status = 'expired'");
        return new MetricDtos.AuditStatsOut(totalTasks, auditedTasks, pendingTasks,
                passCount, failCount, warnCount, reviewers());
    }

    public List<MetricDtos.AlertOut> alerts() {
        return metrics.alerts();
    }

    private Map<String, MetricDtos.ReviewerStatOut> reviewers() {
        Map<String, int[]> grouped = new LinkedHashMap<>();
        jdbc.query("SELECT resolved_by, status FROM approval_items"
                        + " WHERE status IN " + AUDITED + " AND resolved_by IS NOT NULL",
                row -> {
                    String reviewer = row.getString("resolved_by");
                    if (reviewer == null || reviewer.isEmpty()) {
                        return;
                    }
                    int[] bucket = grouped.computeIfAbsent(reviewer, key -> new int[3]);
                    switch (row.getString("status")) {
                        case "approved", "acknowledged" -> bucket[0]++;
                        case "rejected" -> bucket[1]++;
                        default -> bucket[2]++;
                    }
                });
        Map<String, MetricDtos.ReviewerStatOut> result = new LinkedHashMap<>();
        grouped.entrySet().stream()
                .sorted(Comparator.comparingInt(
                        (Map.Entry<String, int[]> entry) -> -total(entry.getValue())))
                .forEach(entry -> {
                    int[] bucket = entry.getValue();
                    result.put(entry.getKey(), new MetricDtos.ReviewerStatOut(
                            bucket[0], bucket[1], bucket[2], total(bucket)));
                });
        return result;
    }

    private static int total(int[] bucket) {
        return bucket[0] + bucket[1] + bucket[2];
    }

    private int count(String sql) {
        Integer value = jdbc.queryForObject(sql, Integer.class);
        return value == null ? 0 : value;
    }
}
