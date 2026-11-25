package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class AgentService {

    private static final Duration HEARTBEAT_TIMEOUT = Duration.ofSeconds(180);
    private static final Duration ROTATION_GRACE = Duration.ofHours(24);

    private final AgentRepository repository;
    private final EmployeeRepository employees;
    private final Ids ids;
    private final Outbox outbox;
    private final TokenCipher cipher;

    public AgentService(AgentRepository repository, EmployeeRepository employees,
                        Ids ids, Outbox outbox, TokenCipher cipher) {
        this.repository = repository;
        this.employees = employees;
        this.ids = ids;
        this.outbox = outbox;
        this.cipher = cipher;
    }

    public AgentDtos.AgentListOut listPage(int limit, int offset) {
        AgentRepository.Page page = repository.listPage(limit, offset);
        Instant now = Instant.now();
        List<AgentDtos.AgentOut> items = page.items().stream()
                .map(agent -> AgentDtos.AgentOut.of(agent, online(agent, now)))
                .toList();
        return new AgentDtos.AgentListOut(items, page.total(), limit, offset);
    }

    public AgentDtos.AgentOut detail(String agentId) {
        Agent agent = load(agentId);
        return AgentDtos.AgentOut.of(agent, online(agent, Instant.now()));
    }

    @Transactional
    public AgentDtos.AgentOut create(Actor actor, AgentDtos.AgentIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        String name = input.name() == null ? "" : input.name().strip();
        if (name.isEmpty()) {
            throw ApiException.conflict("invalid_state", "Agent 名称不能为空");
        }
        Instant now = Instant.now();
        Agent agent = new Agent(ids.next("agent"), name,
                input.framework() == null ? "" : input.framework(),
                input.model(), input.endpoint(),
                input.enabled() == null || input.enabled(), now, now);
        repository.save(agent);
        outbox.enqueue("agents.agent_created", Map.of("agent_id", agent.agentId()));
        return AgentDtos.AgentOut.of(agent, online(agent, now));
    }

    @Transactional
    public AgentDtos.AgentOut update(Actor actor, String agentId, Map<String, Object> fields) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Agent existing = load(agentId);
        String name = fields.containsKey("name") && fields.get("name") != null
                ? String.valueOf(fields.get("name")).strip() : existing.name();
        if (name.isEmpty() || name.length() > 64) {
            throw ApiException.unprocessable();
        }
        validateTypes(fields);
        String framework = fields.containsKey("framework")
                ? nullable(fields.get("framework")) : existing.framework();
        if (framework != null && framework.length() > 64) {
            throw ApiException.unprocessable();
        }
        Agent updated = new Agent(existing.agentId(), name,
                framework == null ? "" : framework,
                fields.containsKey("model") ? nullable(fields.get("model")) : existing.model(),
                fields.containsKey("endpoint") ? nullable(fields.get("endpoint"))
                        : existing.endpoint(),
                fields.containsKey("enabled") && fields.get("enabled") != null
                        ? Boolean.parseBoolean(String.valueOf(fields.get("enabled")))
                        : existing.enabled(),
                existing.createdAt(), Instant.now(), existing.agentType(),
                existing.channelType(), existing.endpointToken(),
                existing.endpointTokenLookupHash(), existing.endpointTokenPrev(),
                existing.endpointTokenPrevLookupHash(), existing.endpointTokenPrevExpiresAt(),
                existing.lastSeenAt(), existing.pendingEndpoint(),
                existing.endpointReviewStatus(), existing.endpointApprovedBy(),
                existing.endpointApprovedAt(), existing.deletedAt(), existing.deletedBy());
        repository.save(updated);
        outbox.enqueue("agents.agent_updated", Map.of("agent_id", agentId));
        return AgentDtos.AgentOut.of(updated, online(updated, Instant.now()));
    }

    @Transactional
    public void delete(Actor actor, String agentId) {
        Authz.require(actor, Authz.AGENT_DEREGISTER);
        load(agentId);
        if (employees.countActiveByAgent(agentId) > 0) {
            throw ApiException.conflict("invalid_state", "Agent 仍被员工绑定，请先解除绑定");
        }
        repository.softDelete(agentId, actor.employeeId());
        outbox.enqueue("agents.agent_deleted", Map.of("agent_id", agentId));
    }

    @Transactional
    public AgentDtos.AgentOut unbind(Actor actor, String agentId) {
        Authz.require(actor, Authz.AGENT_DEREGISTER);
        Agent agent = load(agentId);
        for (Employee employee : employees.listAll()) {
            if (!agentId.equals(employee.agentId()) || "deregistered".equals(employee.status())) {
                continue;
            }
            Employee updated = new Employee(employee.employeeId(), employee.displayName(),
                    employee.accountType(), employee.status(), employee.teamId(),
                    employee.positionId(), employee.seatId(), null, employee.capabilities(),
                    employee.dataScope(), employee.fileScope(), employee.endpoint(),
                    employee.endpointApproved(), employee.approvedAt(), employee.lastHeartbeat());
            employees.save(updated);
            outbox.enqueue("identity.agent_bound", Map.of("employee_id", employee.employeeId(),
                    "agent_id", ""));
        }
        return AgentDtos.AgentOut.of(agent, online(agent, Instant.now()));
    }

    @Transactional
    public AgentDtos.AgentOut approveEndpoint(Actor actor, String agentId) {
        requireAdmin(actor);
        Agent agent = load(agentId);
        if (agent.pendingEndpoint() == null) {
            throw ApiException.invalid("没有待审批的 endpoint");
        }
        Instant now = Instant.now();
        Agent updated = new Agent(agent.agentId(), agent.name(), agent.framework(),
                agent.model(), agent.pendingEndpoint(), agent.enabled(), agent.createdAt(), now,
                agent.agentType(), agent.channelType(), agent.endpointToken(),
                agent.endpointTokenLookupHash(), agent.endpointTokenPrev(),
                agent.endpointTokenPrevLookupHash(), agent.endpointTokenPrevExpiresAt(),
                agent.lastSeenAt(), null, "approved", actor.employeeId(), now,
                agent.deletedAt(), agent.deletedBy());
        repository.save(updated);
        syncEmployeeEndpoint(updated, true);
        outbox.enqueue("agents.endpoint_approved", Map.of("agent_id", agentId));
        return AgentDtos.AgentOut.of(updated, online(updated, now));
    }

    @Transactional
    public AgentDtos.AgentOut rejectEndpoint(Actor actor, String agentId) {
        requireAdmin(actor);
        Agent agent = load(agentId);
        if (agent.pendingEndpoint() == null) {
            throw ApiException.invalid("没有待审批的 endpoint");
        }
        Instant now = Instant.now();
        Agent updated = new Agent(agent.agentId(), agent.name(), agent.framework(),
                agent.model(), agent.endpoint(), agent.enabled(), agent.createdAt(), now,
                agent.agentType(), agent.channelType(), agent.endpointToken(),
                agent.endpointTokenLookupHash(), agent.endpointTokenPrev(),
                agent.endpointTokenPrevLookupHash(), agent.endpointTokenPrevExpiresAt(),
                agent.lastSeenAt(), null, "rejected", actor.employeeId(), now,
                agent.deletedAt(), agent.deletedBy());
        repository.save(updated);
        if (updated.endpoint() == null) {
            syncEmployeeEndpoint(updated, false);
        }
        return AgentDtos.AgentOut.of(updated, online(updated, now));
    }

    @Transactional
    public AgentDtos.AgentTokenOut rotateToken(Actor actor, String agentId) {
        requireAdmin(actor);
        Agent agent = load(agentId);
        Instant now = Instant.now();
        String token = ids.next("mbk");
        String ciphertext = cipher.encrypt(token);
        String digest = cipher.lookupDigest(token);
        Agent updated = new Agent(agent.agentId(), agent.name(), agent.framework(),
                agent.model(), agent.endpoint(), agent.enabled(), agent.createdAt(), now,
                agent.agentType(), agent.channelType(), ciphertext, digest,
                agent.endpointToken(), agent.endpointTokenLookupHash(),
                agent.endpointToken() == null ? null : now.plus(ROTATION_GRACE),
                agent.lastSeenAt(), agent.pendingEndpoint(), agent.endpointReviewStatus(),
                agent.endpointApprovedBy(), agent.endpointApprovedAt(), agent.deletedAt(),
                agent.deletedBy());
        repository.save(updated);
        outbox.enqueue("agents.token_rotated", Map.of("agent_id", agentId));
        return new AgentDtos.AgentTokenOut(agentId, token, cipher.fingerprint(token),
                updated.endpointTokenPrevExpiresAt());
    }

    @Transactional
    public AgentDtos.AgentOut revokeToken(Actor actor, String agentId) {
        requireAdmin(actor);
        Agent agent = load(agentId);
        Instant now = Instant.now();
        Agent updated = new Agent(agent.agentId(), agent.name(), agent.framework(),
                agent.model(), agent.endpoint(), agent.enabled(), agent.createdAt(), now,
                agent.agentType(), agent.channelType(), null, null, null, null, null,
                null, agent.pendingEndpoint(), agent.endpointReviewStatus(),
                agent.endpointApprovedBy(), agent.endpointApprovedAt(), agent.deletedAt(),
                agent.deletedBy());
        repository.save(updated);
        outbox.enqueue("agents.token_revoked", Map.of("agent_id", agentId));
        return AgentDtos.AgentOut.of(updated, false);
    }

    public AgentDtos.AgentHealthOut health(String agentId) {
        Agent agent = load(agentId);
        boolean online = online(agent, Instant.now());
        return new AgentDtos.AgentHealthOut(agentId, online,
                "approved".equals(agent.endpointReviewStatus()) && agent.endpoint() != null,
                agent.lastSeenAt());
    }

    public static boolean online(Agent agent, Instant now) {
        if (agent.deletedAt() != null || !agent.enabled() || agent.lastSeenAt() == null) {
            return false;
        }
        return Duration.between(agent.lastSeenAt(), now).compareTo(HEARTBEAT_TIMEOUT) <= 0;
    }

    public static boolean dispatchable(Agent agent, Instant now) {
        return "approved".equals(agent.endpointReviewStatus())
                && agent.endpoint() != null && online(agent, now);
    }

    public static Actor actorOf(Employee employee) {
        return new Actor(employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.dataScope(),
                employee.fileScope().isEmpty() ? "" : String.join(",", employee.fileScope()),
                employee.endpointApproved(), Set.copyOf(employee.capabilities()));
    }

    public String summaryName(String agentId) {
        return repository.find(agentId).map(Agent::name).orElse(null);
    }

    public String summaryFramework(String agentId) {
        return repository.find(agentId).map(Agent::framework).orElse(null);
    }

    public boolean exists(String agentId) {
        return repository.find(agentId).isPresent();
    }

    private Agent load(String agentId) {
        return repository.find(agentId).orElseThrow(() -> ApiException.notFound("Agent 不存在"));
    }

    private void requireAdmin(Actor actor) {
        Authz.ensureAnyAllowed(actor, Set.of(Authz.SYSTEM_CONFIG, Authz.CONSOLE_ADMIN),
                Authz.Resource.of("agent"));
    }

    private void syncEmployeeEndpoint(Agent agent, boolean approved) {
        for (Employee employee : employees.listAll()) {
            if (!agent.agentId().equals(employee.agentId())) {
                continue;
            }
            Employee updated = new Employee(employee.employeeId(), employee.displayName(),
                    employee.accountType(), employee.status(), employee.teamId(),
                    employee.positionId(), employee.seatId(), employee.agentId(),
                    employee.capabilities(), employee.dataScope(), employee.fileScope(),
                    agent.endpoint(), approved && agent.endpoint() != null,
                    employee.approvedAt(), employee.lastHeartbeat());
            employees.save(updated);
        }
    }

    private void validateTypes(Map<String, Object> fields) {
        if (fields.get("framework") != null && !(fields.get("framework") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("model") != null && !(fields.get("model") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("endpoint") != null && !(fields.get("endpoint") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("enabled") != null && !(fields.get("enabled") instanceof Boolean)) {
            throw ApiException.unprocessable();
        }
    }

    private String nullable(Object value) {
        return value == null ? null : String.valueOf(value);
    }
}
