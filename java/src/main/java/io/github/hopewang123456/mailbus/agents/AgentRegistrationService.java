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

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class AgentRegistrationService {

    private final AgentRepository repository;
    private final EmployeeRepository employees;
    private final Ids ids;
    private final Outbox outbox;
    private final TokenCipher cipher;

    public AgentRegistrationService(AgentRepository repository, EmployeeRepository employees,
                                    Ids ids, Outbox outbox, TokenCipher cipher) {
        this.repository = repository;
        this.employees = employees;
        this.ids = ids;
        this.outbox = outbox;
        this.cipher = cipher;
    }

    @Transactional
    public AgentDtos.AgentInviteOut createInvite(Actor actor, AgentDtos.AgentInviteIn input) {
        Authz.require(actor, Authz.CONSOLE_ADMIN);
        List<String> permissions = input.permissions() == null ? List.of()
                : input.permissions().stream().map(String::strip).filter(v -> !v.isBlank()).toList();
        if (!actor.has(Authz.ALL) && !actor.capabilities().containsAll(permissions)) {
            throw ApiException.forbidden("不能授予超出自身权限的邀请码");
        }
        Instant now = Instant.now();
        String code = ids.next("mbreg");
        AgentInvite invite = new AgentInvite(ids.next("ainv"), sha256(code),
                input.employeeName(), input.positionId(),
                input.capabilities() == null ? List.of() : input.capabilities(),
                permissions.isEmpty() ? List.of("message_read", "message_send", "result_submit")
                        : permissions,
                input.dataScope() == null ? "self" : input.dataScope(),
                input.agentType() == null ? "external" : input.agentType(),
                input.channelType() == null ? "a2a" : input.channelType(),
                input.expiresInHours() == null ? null
                        : now.plus(input.expiresInHours(), ChronoUnit.HOURS),
                actor.employeeId(), now, null, null, null, null);
        repository.addInvite(invite);
        return toView(invite, code);
    }

    public AgentDtos.AgentInviteListOut listInvites(int limit, int offset) {
        AgentRepository.InvitePage page = repository.listInvites(limit, offset);
        return new AgentDtos.AgentInviteListOut(
                page.items().stream().map(item -> toView(item, null)).toList(),
                page.total(), limit, offset);
    }

    @Transactional
    public AgentDtos.AgentInviteOut revokeInvite(Actor actor, String inviteId) {
        Authz.require(actor, Authz.CONSOLE_ADMIN);
        AgentInvite invite = repository.findInvite(inviteId)
                .orElseThrow(() -> ApiException.notFound("邀请码不存在"));
        if (invite.revokedAt() != null) {
            throw ApiException.invalid("邀请码已作废");
        }
        AgentInvite updated = new AgentInvite(invite.inviteId(), invite.codeHash(),
                invite.employeeName(), invite.positionId(), invite.capabilities(),
                invite.permissions(), invite.dataScope(), invite.agentType(),
                invite.channelType(), invite.expiresAt(), invite.createdBy(),
                invite.createdAt(), invite.usedByAgentId(), invite.usedAt(),
                Instant.now(), actor.employeeId());
        repository.saveInvite(updated);
        return toView(updated, null);
    }

    @Transactional
    public AgentDtos.AgentRegisterOut register(AgentDtos.AgentRegisterIn input) {
        Instant now = Instant.now();
        AgentInvite invite = repository.findInviteByHash(sha256(input.inviteCode()))
                .orElseThrow(() -> ApiException.notFound("邀请码无效"));
        ensureUsable(invite, now);
        if (invite.positionId() == null || invite.positionId().isBlank()) {
            throw ApiException.unprocessable("unprocessable", "Agent 员工缺少岗位，无法注册");
        }
        String endpoint = input.endpoint() == null || input.endpoint().isBlank()
                ? null : EndpointGuard.validate(input.endpoint());
        String token = ids.next("mbk");
        boolean pending = endpoint != null;
        Agent agent = new Agent(ids.next("agent"), input.name().strip(),
                input.framework() == null ? "" : input.framework().strip(), input.model(),
                null, true, now, now, invite.agentType(), invite.channelType(),
                cipher.encrypt(token), cipher.lookupDigest(token), null, null, null,
                now, endpoint, pending ? "pending" : "approved", null,
                pending ? null : now, null, null);
        repository.save(agent);
        String employeeId = ids.next("emp");
        Employee employee = new Employee(employeeId,
                invite.employeeName() == null ? input.name().strip() : invite.employeeName(),
                "agent", "active", null, invite.positionId(), null, agent.agentId(),
                Set.copyOf(invite.permissions()), invite.dataScope(), List.of(), endpoint,
                false, now, now);
        employees.save(employee);
        employees.saveSkills(employeeId, invite.capabilities());
        repository.saveInvite(new AgentInvite(invite.inviteId(), invite.codeHash(),
                invite.employeeName(), invite.positionId(), invite.capabilities(),
                invite.permissions(), invite.dataScope(), invite.agentType(),
                invite.channelType(), invite.expiresAt(), invite.createdBy(),
                invite.createdAt(), agent.agentId(), now, invite.revokedAt(),
                invite.revokedBy()));
        outbox.enqueue("agents.agent_registered", Map.of("agent_id", agent.agentId()));
        return new AgentDtos.AgentRegisterOut(agent.agentId(), employeeId, token, endpoint,
                agent.endpointReviewStatus());
    }

    private void ensureUsable(AgentInvite invite, Instant now) {
        if (invite.usedAt() != null) {
            throw ApiException.conflict("invalid_state", "邀请码已被使用");
        }
        if (invite.revokedAt() != null) {
            throw ApiException.gone("resource_gone", "邀请码已作废");
        }
        if (invite.expiresAt() != null && !invite.expiresAt().isAfter(now)) {
            throw ApiException.gone("resource_gone", "邀请码已过期");
        }
    }

    private String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.strip().getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 不可用", exception);
        }
    }

    private AgentDtos.AgentInviteOut toView(AgentInvite invite, String code) {
        return new AgentDtos.AgentInviteOut(invite.inviteId(), code, invite.employeeName(),
                invite.positionId(), invite.capabilities(), invite.permissions(),
                invite.dataScope(), invite.agentType(), invite.channelType(),
                invite.createdBy(), invite.createdAt(), invite.expiresAt(),
                invite.usedByAgentId(), invite.usedAt(), invite.revokedAt());
    }
}
