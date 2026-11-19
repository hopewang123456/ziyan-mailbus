package io.github.hopewang123456.mailbus.observability;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class OverviewService {

    private static final Set<String> ACTIVE_TASKS = Set.of("queued", "running", "blocked");

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public OverviewService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public ObservabilityDtos.OverviewOut get() {
        int employeesTotal = count("SELECT COUNT(*) FROM identity_employees");
        int employeesActive = count("SELECT COUNT(*) FROM identity_employees WHERE status = 'active'");
        int employeesPending = count("SELECT COUNT(*) FROM identity_employees WHERE status = 'pending'");
        int employeesOffline = count("SELECT COUNT(*) FROM identity_employees WHERE status = 'offline'");
        int seatsOccupied = count("""
                SELECT COUNT(*) FROM identity_employees
                 WHERE seat_id IS NOT NULL AND status <> 'deregistered'
                """);
        int agentsTotal = count("SELECT COUNT(*) FROM agents");
        int agentsEnabled = count("SELECT COUNT(*) FROM agents WHERE enabled = 1");
        int agentsOnline = count("""
                SELECT COUNT(*) FROM identity_employees e
                  JOIN agents a ON a.agent_id = e.agent_id AND a.enabled = 1
                 WHERE e.status = 'active' AND e.agent_id IS NOT NULL
                """);
        int agentsBusy = count("""
                SELECT COUNT(DISTINCT e.agent_id) FROM identity_employees e
                  JOIN agents a ON a.agent_id = e.agent_id AND a.enabled = 1
                  JOIN task_tasks t ON t.owner_id = e.employee_id
                 WHERE e.status = 'active' AND e.agent_id IS NOT NULL
                   AND t.state IN ('queued', 'running', 'blocked')
                """);
        int teams = count("SELECT COUNT(*) FROM org_teams");
        int positions = count("SELECT COUNT(*) FROM org_positions");
        int tasksTotal = count("SELECT COUNT(*) FROM task_tasks");
        int tasksActive = count("SELECT COUNT(*) FROM task_tasks WHERE state IN ('queued','running','blocked')");
        int tasksRunning = count("SELECT COUNT(*) FROM task_tasks WHERE state = 'running'");
        int tasksBlocked = count("SELECT COUNT(*) FROM task_tasks WHERE state = 'blocked'");
        int tasksDone = count("SELECT COUNT(*) FROM task_tasks WHERE state = 'done'");
        long startOfDay = LocalDate.now(ZoneOffset.UTC).atStartOfDay().toEpochSecond(ZoneOffset.UTC);
        int tasksFailedToday = count(
                "SELECT COUNT(*) FROM task_tasks WHERE state = 'failed' AND updated_at >= ?",
                startOfDay);
        int approvalsPending = count("SELECT COUNT(*) FROM approval_items WHERE status = 'pending'");
        int messagesTotal = count("SELECT COUNT(*) FROM msg_messages");
        int skillsTotal = count("SELECT COUNT(*) FROM skills_packages");
        int skillsEnabled = count("SELECT COUNT(*) FROM skills_packages WHERE enabled = 1");
        int workflowsTotal = count("SELECT COUNT(*) FROM wf_defs");
        int workflowsPublished = count(
                "SELECT COUNT(*) FROM wf_defs WHERE published_version IS NOT NULL");
        List<ObservabilityDtos.MetricPoint> metrics = List.of(
                new ObservabilityDtos.MetricPoint("tasks.active", tasksActive, "count"),
                new ObservabilityDtos.MetricPoint("tasks.failed_today", tasksFailedToday, "count"),
                new ObservabilityDtos.MetricPoint("bus.messages_total", messagesTotal, "count"),
                new ObservabilityDtos.MetricPoint("agents.online", agentsOnline, "count"),
                new ObservabilityDtos.MetricPoint("agents.total", agentsTotal, "count"),
                new ObservabilityDtos.MetricPoint("humanqueue.pending", approvalsPending, "count"),
                new ObservabilityDtos.MetricPoint("skills.total", skillsTotal, "count"),
                new ObservabilityDtos.MetricPoint("workflows.total", workflowsTotal, "count"));
        return new ObservabilityDtos.OverviewOut(employeesTotal, employeesActive,
                employeesPending, employeesOffline, agentsTotal, agentsEnabled, agentsOnline,
                agentsBusy, teams, positions, seatsOccupied, tasksTotal, tasksActive,
                tasksRunning, tasksBlocked, tasksDone, tasksFailedToday, approvalsPending,
                messagesTotal, skillsTotal, skillsEnabled, workflowsTotal, workflowsPublished,
                metrics);
    }

    public List<ObservabilityDtos.LogEntryOut> log(int limit) {
        int size = Math.max(1, Math.min(limit, 500));
        return jdbc.query("""
                SELECT * FROM ops_outbox ORDER BY created_at DESC, event_id DESC LIMIT ?
                """, (row, index) -> new ObservabilityDtos.LogEntryOut(
                row.getString("event_id"), row.getString("kind"),
                payload(row.getString("payload")), row.getInt("attempts"),
                Instant.ofEpochSecond((long) row.getDouble("created_at"))), size);
    }

    private int count(String sql, Object... args) {
        Integer value = jdbc.queryForObject(sql, Integer.class, args);
        return value == null ? 0 : value;
    }

    private Map<String, Object> payload(String value) {
        try {
            return objectMapper.readValue(value == null ? "{}" : value,
                    new TypeReference<Map<String, Object>>() {
                    });
        } catch (Exception exception) {
            return Map.of();
        }
    }
}
