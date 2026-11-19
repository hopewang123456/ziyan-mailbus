package io.github.hopewang123456.mailbus.observability;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class ObservabilityDtos {

    private ObservabilityDtos() {
    }

    public record MetricPoint(String metric, Number value, String unit) {
    }

    public record OverviewOut(int employeesTotal, int employeesActive, int employeesPending,
                              int employeesOffline, int agentsTotal, int agentsEnabled,
                              int agentsOnline, int agentsBusy, int teams, int positions,
                              int seatsOccupied, int tasksTotal, int tasksActive,
                              int tasksRunning, int tasksBlocked, int tasksDone,
                              int tasksFailedToday, int approvalsPending, int messagesTotal,
                              int skillsTotal, int skillsEnabled, int workflowsTotal,
                              int workflowsPublished, List<MetricPoint> metrics) {
    }

    public record LogEntryOut(String eventId, String kind, Map<String, Object> payload,
                              int attempts, Instant createdAt) {
    }
}
