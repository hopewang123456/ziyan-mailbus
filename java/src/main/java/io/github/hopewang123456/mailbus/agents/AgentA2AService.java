package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import io.github.hopewang123456.mailbus.workflow.TaskDtos;
import io.github.hopewang123456.mailbus.workflow.TaskRepository;
import io.github.hopewang123456.mailbus.workflow.TaskService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

@Service
public class AgentA2AService {

    private static final Set<String> FAILED = Set.of(
            "failed", "rejected", "needs_human", "needs_info");

    private final AgentRepository repository;
    private final EmployeeRepository employees;
    private final TaskRepository tasks;
    private final TaskService taskService;
    private final TokenCipher cipher;
    private final Ids ids;
    private final Outbox outbox;

    public AgentA2AService(AgentRepository repository, EmployeeRepository employees,
                           TaskRepository tasks, TaskService taskService,
                           TokenCipher cipher, Ids ids, Outbox outbox) {
        this.repository = repository;
        this.employees = employees;
        this.tasks = tasks;
        this.taskService = taskService;
        this.cipher = cipher;
        this.ids = ids;
        this.outbox = outbox;
    }

    public Agent authenticate(String token) {
        if (token == null || token.isBlank()) {
            throw ApiException.unauthorized("缺少 Agent token");
        }
        Agent agent = repository.findByTokenLookup(cipher.lookupDigest(token)).orElse(null);
        if (agent == null || !agent.enabled() || agent.deletedAt() != null) {
            throw ApiException.unauthorized("Agent token 无效");
        }
        return agent;
    }

    @Transactional
    public AgentDtos.A2aAckOut handle(Agent agent, AgentDtos.A2aMessageIn message) {
        if ("heartbeat".equals(message.type())) {
            heartbeat(agent, message);
            return ack(message, false);
        }
        if ("result".equals(message.type())) {
            return result(agent, message);
        }
        if ("message".equals(message.type())) {
            outbox.enqueue("a2a.message_received", Map.of("agent_id", agent.agentId()));
        }
        return ack(message, false);
    }

    private void heartbeat(Agent agent, AgentDtos.A2aMessageIn message) {
        Instant now = Instant.now();
        String endpoint = message.endpoint() == null || message.endpoint().isBlank()
                ? null : EndpointGuard.validate(message.endpoint());
        String pending = agent.pendingEndpoint();
        String status = agent.endpointReviewStatus();
        if (endpoint != null && !endpoint.equals(agent.endpoint())
                && !endpoint.equals(agent.pendingEndpoint())) {
            pending = endpoint;
            status = "pending";
        }
        Agent updated = new Agent(agent.agentId(), agent.name(), agent.framework(),
                agent.model(), agent.endpoint(), agent.enabled(), agent.createdAt(), now,
                agent.agentType(), agent.channelType(), agent.endpointToken(),
                agent.endpointTokenLookupHash(), agent.endpointTokenPrev(),
                agent.endpointTokenPrevLookupHash(), agent.endpointTokenPrevExpiresAt(),
                now, pending, status, agent.endpointApprovedBy(), agent.endpointApprovedAt(),
                agent.deletedAt(), agent.deletedBy());
        repository.save(updated);
        for (Employee employee : employees.listAll()) {
            if (!agent.agentId().equals(employee.agentId())) {
                continue;
            }
            String next = "deregistered".equals(employee.status()) ? "deregistered" : "active";
            employees.save(new Employee(employee.employeeId(), employee.displayName(),
                    employee.accountType(), next, employee.teamId(), employee.positionId(),
                    employee.seatId(), employee.agentId(), employee.capabilities(),
                    employee.dataScope(), employee.fileScope(), employee.endpoint(),
                    employee.endpointApproved(), employee.approvedAt(), now));
        }
    }

    private AgentDtos.A2aAckOut result(Agent agent, AgentDtos.A2aMessageIn message) {
        if (message.runId() == null || message.runId().isBlank()) {
            throw ApiException.unprocessable("unprocessable", "result 必须携带 run_id");
        }
        if (message.attemptNo() == null) {
            throw ApiException.unprocessable("unprocessable", "result 必须携带 attempt_no");
        }
        TaskRepository.RunRow run = tasks.findRun(message.runId());
        if (run == null) {
            throw stale("执行实例不存在");
        }
        Employee employee = employees.find(run.assignedEmployeeId()).orElse(null);
        if (employee == null || !agent.agentId().equals(employee.agentId())) {
            throw ApiException.forbidden("该执行实例不属于当前 Agent");
        }
        String result = compose(message);
        if (run.attemptNo() != message.attemptNo()) {
            throw stale("执行实例 attempt 已过期");
        }
        if ("done".equals(run.state()) || "failed".equals(run.state())) {
            if (Objects.equals(run.result(), result)) {
                return ack(message, true);
            }
            throw stale("该执行实例已提交过其他结果");
        }
        List<String> artifactIds = message.artifacts() == null ? List.of()
                : message.artifacts().stream()
                .filter(item -> "artifact".equals(item.type()) && item.artifactId() != null)
                .map(AgentDtos.A2aArtifactIn::artifactId).toList();
        taskService.submit(AgentService.actorOf(employee), run.taskId(), run.nodeId(),
                new TaskDtos.ResultIn(message.attemptNo(), result, artifactIds));
        return ack(message, false);
    }

    private String compose(AgentDtos.A2aMessageIn message) {
        String status = message.status() == null ? "completed" : message.status();
        Map<String, Object> payload = message.payload() == null
                ? new LinkedHashMap<>() : new LinkedHashMap<>(message.payload());
        if (message.output() != null) {
            payload.putIfAbsent("output", message.output());
        }
        if (FAILED.contains(status)) {
            payload.put("status", status);
            return toJson(payload);
        }
        if (!payload.isEmpty()) {
            payload.putIfAbsent("status", "completed");
            return toJson(payload);
        }
        return message.output() != null ? message.output() : "{\"status\":\"completed\"}";
    }

    private String toJson(Map<String, Object> payload) {
        StringBuilder builder = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : payload.entrySet()) {
            if (!first) {
                builder.append(',');
            }
            first = false;
            builder.append('"').append(entry.getKey()).append("\":");
            Object value = entry.getValue();
            if (value == null) {
                builder.append("null");
            } else if (value instanceof Number || value instanceof Boolean) {
                builder.append(value);
            } else {
                builder.append('"').append(String.valueOf(value)
                        .replace("\\", "\\\\").replace("\"", "\\\"")).append('"');
            }
        }
        return builder.append('}').toString();
    }

    private ApiException stale(String message) {
        return ApiException.conflict("stale_run", message);
    }

    private AgentDtos.A2aAckOut ack(AgentDtos.A2aMessageIn message, boolean duplicate) {
        return new AgentDtos.A2aAckOut(
                message.messageId() == null ? ids.next("ack") : message.messageId(),
                true, duplicate);
    }
}
