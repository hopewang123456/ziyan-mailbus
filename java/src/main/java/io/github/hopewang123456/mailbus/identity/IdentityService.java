package io.github.hopewang123456.mailbus.identity;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.agents.Agent;
import io.github.hopewang123456.mailbus.agents.AgentRepository;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.common.Tokens;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.events.Outbox;
import io.github.hopewang123456.mailbus.org.OrgDtos;
import io.github.hopewang123456.mailbus.org.OrgService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.github.hopewang123456.mailbus.identity.IdentityDtos.*;

@Service
public class IdentityService {

    private static final List<String> STEPS = List.of("super_admin", "model_config", "first_team");
    private static final Set<String> SKIPPABLE = Set.of("model_config", "first_team");
    private static final Set<String> MANAGER_CAPABILITIES = Set.of(
            "console_admin", "employee_invite", "org_manage", "hitl_request", "hitl_resolve",
            "task_create", "task_dispatch", "workflow_create", "workflow_modify",
            "message_send", "log_read");
    private static final Set<String> ON_DUTY = Set.of("active", "offline");

    private final JdbcTemplate jdbc;
    private final EmployeeRepository employees;
    private final AgentRepository agents;
    private final OrgService org;
    private final Ids ids;
    private final Outbox outbox;
    private final ObjectMapper objectMapper;
    private final AppProperties properties;

    public IdentityService(JdbcTemplate jdbc, EmployeeRepository employees, AgentRepository agents,
                           OrgService org, Ids ids, Outbox outbox, ObjectMapper objectMapper,
                           AppProperties properties) {
        this.jdbc = jdbc;
        this.employees = employees;
        this.agents = agents;
        this.org = org;
        this.ids = ids;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    // ---------- bootstrap ----------

    public BootstrapStatusOut bootstrapStatus() {
        Set<String> done = completedSteps();
        List<BootstrapStep> steps = new ArrayList<>();
        for (String step : STEPS) {
            steps.add(new BootstrapStep(step, done.contains(step), SKIPPABLE.contains(step)));
        }
        return new BootstrapStatusOut(done.containsAll(STEPS), steps);
    }

    @Transactional
    public SessionOut createSuperAdmin(SuperAdminIn input) {
        if (completedSteps().contains("super_admin")) {
            throw ApiException.conflict("idempotency_conflict", "超级管理员已创建");
        }
        Instant now = Instant.now();
        String employeeId = input.employeeId() == null || input.employeeId().isBlank()
                ? ids.next("emp") : input.employeeId();
        Employee employee = new Employee(employeeId, input.displayName(), "human", "active",
                null, null, null, null, Set.of("*"), "global", List.of(), null, false,
                now, now);
        employees.save(employee);
        markStep("super_admin", Map.of("employee_id", employeeId));
        String token = issueSession(employeeId, now);
        outbox.enqueue("identity.super_admin_created", Map.of("employee_id", employeeId));
        return new SessionOut(view(employee, null), token);
    }

    @Transactional
    public BootstrapStatusOut configureModel(Actor actor, ModelConfigIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("provider", input.provider());
        detail.put("model", input.model());
        if (input.apiBase() != null) {
            detail.put("api_base", input.apiBase());
        }
        markStep("model_config", detail);
        return bootstrapStatus();
    }

    @Transactional
    public OrgDtos.TeamOut createFirstTeam(Actor actor, OrgDtos.TeamIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Map<String, Object> detail = stepDetail("first_team");
        String existingId = stringValue(detail.get("team_id"));
        if (existingId != null) {
            List<OrgDtos.TeamOut> teams = jdbc.query(
                    "SELECT team_id, name FROM org_teams WHERE team_id = ?",
                    (row, index) -> new OrgDtos.TeamOut(row.getString("team_id"),
                            row.getString("name")), existingId);
            if (!teams.isEmpty()) {
                return teams.get(0);
            }
        }
        OrgDtos.TeamOut team = org.createTeam(actor,
                new OrgDtos.TeamIn(input.name(),
                        input.teamId() == null || input.teamId().isBlank()
                                ? ids.next("team") : input.teamId()));
        markStep("first_team", Map.of("team_id", team.teamId(), "name", team.name()));
        return team;
    }

    @Transactional
    public BootstrapStatusOut skip(Actor actor, String step) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        if (!STEPS.contains(step)) {
            throw ApiException.conflict("invalid_state", "未知引导步骤：" + step);
        }
        if (!SKIPPABLE.contains(step)) {
            throw ApiException.conflict("invalid_state", "超级管理员步骤不可跳过");
        }
        if (!completedSteps().contains(step)) {
            markStep(step, Map.of("skipped", true));
        }
        return bootstrapStatus();
    }

    // ---------- staff ----------

    @Transactional
    public ApplyOut apply(ApplyIn input) {
        Instant now = Instant.now();
        String employeeId = ids.next("emp");
        if (input.inviteCode() != null && !input.inviteCode().isBlank()) {
            Invite invite = invite(input.inviteCode());
            validateInvite(invite, input.accountType(), now);
            int consumed = jdbc.update("""
                    UPDATE identity_invites SET consumed_by = ?, consumed_at = ?
                     WHERE invite_code = ? AND consumed_at IS NULL
                    """, employeeId, now.getEpochSecond(), invite.inviteCode());
            if (consumed == 0) {
                throw ApiException.domain("invite_invalid", "邀请码已被使用");
            }
            Set<String> capabilities = new HashSet<>(invite.capabilities());
            capabilities.addAll(org.positionCapabilities(invite.positionId()));
            Employee employee = new Employee(employeeId, input.displayName(), invite.accountType(),
                    "active", invite.teamId(), invite.positionId(), input.seatId(),
                    input.agentId(), capabilities, invite.dataScope(), List.of(),
                    input.endpoint(), false, now, now);
            employees.save(employee);
            String token = issueSession(employeeId, now);
            outbox.enqueue("identity.application_submitted", Map.of("employee_id", employeeId));
            return new ApplyOut(view(employee, null), token);
        }
        Set<String> capabilities = new HashSet<>();
        org.positionForSeat(input.seatId())
                .ifPresent(position -> capabilities.addAll(org.positionCapabilities(position)));
        Employee employee = new Employee(employeeId, input.displayName(), input.accountType(),
                "pending", null, null, input.seatId(), input.agentId(), capabilities, "self",
                List.of(), input.endpoint(), false, null, null);
        employees.save(employee);
        outbox.enqueue("identity.application_submitted", Map.of("employee_id", employeeId));
        return new ApplyOut(view(employee, null), null);
    }

    @Transactional
    public EmployeeView review(Actor actor, String employeeId, ReviewIn input) {
        Authz.require(actor, Authz.EMPLOYEE_INVITE);
        Employee employee = load(employeeId);
        requireStatus(employee, "pending", "只有待审核申请可以审核");
        if (employee.approvedAt() != null) {
            throw ApiException.conflict("invalid_state", "申请已通过审核，请直接激活");
        }
        boolean approved = Boolean.TRUE.equals(input.approved());
        Employee updated = new Employee(employee.employeeId(), employee.displayName(),
                employee.accountType(), approved ? "pending" : "deregistered",
                employee.teamId(), employee.positionId(), employee.seatId(), employee.agentId(),
                employee.capabilities(), employee.dataScope(), employee.fileScope(),
                employee.endpoint(), employee.endpointApproved(),
                approved ? Instant.now() : employee.approvedAt(), employee.lastHeartbeat());
        employees.save(updated);
        outbox.enqueue(approved ? "identity.application_approved"
                : "identity.application_rejected", Map.of("employee_id", employeeId));
        return view(updated, null);
    }

    @Transactional
    public SessionOut activate(Actor actor, String employeeId) {
        Authz.require(actor, Authz.EMPLOYEE_INVITE);
        Employee employee = load(employeeId);
        requireStatus(employee, "pending", "只有待激活账号可以激活");
        if (employee.approvedAt() == null) {
            throw ApiException.conflict("invalid_transition", "申请尚未通过审核");
        }
        Instant now = Instant.now();
        Employee updated = new Employee(employee.employeeId(), employee.displayName(),
                employee.accountType(), "active", employee.teamId(), employee.positionId(),
                employee.seatId(), employee.agentId(), employee.capabilities(),
                employee.dataScope(), employee.fileScope(), employee.endpoint(),
                employee.endpointApproved(), employee.approvedAt(), now);
        employees.save(updated);
        outbox.enqueue("identity.employee_activated", Map.of("employee_id", employeeId));
        return new SessionOut(view(updated, null), issueSession(employeeId, now));
    }

    @Transactional
    public EmployeeView heartbeat(Actor actor, String employeeId) {
        if (!actor.employeeId().equals(employeeId)) {
            throw ApiException.forbidden("只能上报自己的心跳");
        }
        Employee employee = load(employeeId);
        if ("pending".equals(employee.status())) {
            throw ApiException.conflict("invalid_transition", "账号尚未激活");
        }
        if ("deregistered".equals(employee.status())) {
            throw ApiException.conflict("invalid_transition", "账号已注销");
        }
        Employee updated = copy(employee, "active", employee.seatId(), employee.agentId(),
                employee.capabilities(), Instant.now());
        employees.save(updated);
        return view(updated, null);
    }

    @Transactional
    public EmployeeView deregister(Actor actor, String employeeId, String reason) {
        Authz.require(actor, Authz.EMPLOYEE_REMOVE);
        Employee employee = load(employeeId);
        if ("deregistered".equals(employee.status())) {
            return view(employee, null);
        }
        Employee updated = copy(employee, "deregistered", null, employee.agentId(),
                employee.capabilities(), employee.lastHeartbeat());
        employees.save(updated);
        employees.revokeSessions(employeeId);
        outbox.enqueue("identity.employee_deregistered", Map.of("employee_id", employeeId,
                "reason", reason == null ? "" : reason));
        return view(updated, null);
    }

    @Transactional
    public EmployeeView setSeat(Actor actor, String employeeId, String seatId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        Employee employee = load(employeeId);
        if ("deregistered".equals(employee.status())) {
            throw ApiException.conflict("invalid_state", "已注销员工不能分配工位");
        }
        if (seatId != null) {
            if (!org.seatExists(seatId)) {
                throw ApiException.notFound("工位不存在");
            }
            for (Employee other : employees.listAll()) {
                if (!other.employeeId().equals(employeeId) && seatId.equals(other.seatId())
                        && !"deregistered".equals(other.status())) {
                    throw ApiException.conflict("invalid_state", "工位已被 " + other.displayName() + " 占用");
                }
            }
        }
        Set<String> capabilities = new HashSet<>(employee.capabilities());
        org.positionForSeat(seatId)
                .ifPresent(position -> capabilities.addAll(org.positionCapabilities(position)));
        Employee updated = copy(employee, employee.status(), seatId, employee.agentId(),
                capabilities, employee.lastHeartbeat());
        employees.save(updated);
        outbox.enqueue("identity.seat_assigned", Map.of("employee_id", employeeId,
                "seat_id", seatId == null ? "" : seatId));
        return view(updated, null);
    }

    @Transactional
    public EmployeeView bindAgent(Actor actor, String employeeId, String agentId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        Employee employee = load(employeeId);
        if (agentId != null && agents.find(agentId).isEmpty()) {
            throw ApiException.notFound("Agent 不存在");
        }
        if ("deregistered".equals(employee.status())) {
            throw ApiException.conflict("invalid_state", "已注销员工不能绑定 Agent");
        }
        Employee updated = copy(employee, employee.status(), employee.seatId(), agentId,
                employee.capabilities(), employee.lastHeartbeat());
        employees.save(updated);
        outbox.enqueue("identity.agent_bound", Map.of("employee_id", employeeId,
                "agent_id", agentId == null ? "" : agentId));
        return view(updated, null);
    }

    @Transactional
    public EmployeeView reviewEndpoint(Actor actor, String employeeId, boolean approved) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Employee employee = load(employeeId);
        if (approved && (employee.endpoint() == null || employee.endpoint().isBlank())) {
            throw ApiException.conflict("invalid_state", "员工尚未登记端点，无法通过审核");
        }
        Employee updated = new Employee(employee.employeeId(), employee.displayName(),
                employee.accountType(), employee.status(), employee.teamId(),
                employee.positionId(), employee.seatId(), employee.agentId(),
                employee.capabilities(), employee.dataScope(), employee.fileScope(),
                employee.endpoint(), approved, employee.approvedAt(), employee.lastHeartbeat());
        employees.save(updated);
        outbox.enqueue("identity.endpoint_reviewed", Map.of("employee_id", employeeId,
                "approved", approved));
        return view(updated, null);
    }

    @Transactional
    public EmployeeView setManager(Actor actor, String employeeId, boolean enabled) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Employee employee = load(employeeId);
        if ("deregistered".equals(employee.status())) {
            throw ApiException.conflict("invalid_state", "已注销员工不能设为管理者");
        }
        Set<String> capabilities = new HashSet<>(employee.capabilities());
        if (enabled) {
            capabilities.addAll(MANAGER_CAPABILITIES);
        } else {
            capabilities.remove("console_admin");
        }
        Employee updated = copy(employee, employee.status(), employee.seatId(), employee.agentId(),
                capabilities, employee.lastHeartbeat());
        employees.save(updated);
        return view(updated, null);
    }

    public List<EmployeeView> listStaff(Actor actor, String status) {
        Authz.require(actor, Authz.EMPLOYEE_INVITE);
        Map<String, Agent> agentMap = agentMap();
        return employees.listAll().stream()
                .filter(employee -> switch (status == null ? "pending" : status) {
                    case "pending" -> "pending".equals(employee.status());
                    case "active" -> ON_DUTY.contains(employee.status());
                    default -> true;
                })
                .map(employee -> view(employee, agentMap.get(employee.agentId())))
                .toList();
    }

    public EmployeeView get(Actor actor, String employeeId) {
        Employee employee = load(employeeId);
        if (!actor.employeeId().equals(employeeId)) {
            Authz.require(actor, Authz.EMPLOYEE_INVITE);
        }
        return view(employee, null);
    }

    public EmployeeView me(Actor actor) {
        return view(load(actor.employeeId()), null);
    }

    @Transactional
    public InviteOut issueInvite(Actor actor, InviteIn input) {
        Authz.require(actor, Authz.EMPLOYEE_INVITE);
        String accountType = input.accountType();
        if (!"human".equals(accountType) && !"agent".equals(accountType)) {
            throw ApiException.badRequest("account_type 必须是 human 或 agent");
        }
        int hours = input.expiresInHours() == null ? 72 : input.expiresInHours();
        Instant now = Instant.now();
        Instant expiresAt = now.plusSeconds(hours * 3600L);
        String code = ids.next("inv");
        List<String> capabilities = input.capabilities() == null ? List.of()
                : input.capabilities().stream().distinct().sorted().toList();
        String dataScope = input.dataScope() == null ? "self" : input.dataScope();
        jdbc.update("""
                INSERT INTO identity_invites
                    (invite_code, account_type, team_id, position_id, data_scope, capabilities,
                     created_by, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, code, accountType, input.teamId(), input.positionId(), dataScope,
                json(capabilities), actor.employeeId(), now.getEpochSecond(),
                expiresAt.getEpochSecond());
        return new InviteOut(code, accountType, input.teamId(), input.positionId(), dataScope,
                capabilities, expiresAt);
    }

    public void logout(String token) {
        jdbc.update("""
                UPDATE identity_sessions SET revoked_at = ?
                 WHERE token_hash = ? AND revoked_at IS NULL
                """, Instant.now().getEpochSecond(), Tokens.hash(token));
    }

    public int markStaleOffline(long cutoffEpochSeconds) {
        int count = 0;
        for (Employee employee : employees.listAll()) {
            if (!"active".equals(employee.status())) {
                continue;
            }
            if (employee.lastHeartbeat() != null
                    && employee.lastHeartbeat().getEpochSecond() >= cutoffEpochSeconds) {
                continue;
            }
            Employee updated = copy(employee, "offline", employee.seatId(), employee.agentId(),
                    employee.capabilities(), employee.lastHeartbeat());
            employees.save(updated);
            outbox.enqueue("identity.employee_offline",
                    Map.of("employee_id", employee.employeeId()));
            count++;
        }
        return count;
    }

    // ---------- helpers ----------

    private Employee load(String employeeId) {
        return employees.find(employeeId)
                .orElseThrow(() -> ApiException.notFound("员工不存在"));
    }

    private Employee copy(Employee employee, String status, String seatId, String agentId,
                          Set<String> capabilities, Instant lastHeartbeat) {
        return new Employee(employee.employeeId(), employee.displayName(), employee.accountType(),
                status, employee.teamId(), employee.positionId(), seatId, agentId,
                capabilities, employee.dataScope(), employee.fileScope(), employee.endpoint(),
                employee.endpointApproved(), employee.approvedAt(), lastHeartbeat);
    }

    private EmployeeView view(Employee employee, Agent agent) {
        Agent bound = agent;
        if (bound == null && employee.agentId() != null) {
            bound = agents.find(employee.agentId()).orElse(null);
        }
        return new EmployeeView(
                employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.positionId(), employee.seatId(),
                employee.agentId(), bound == null ? null : bound.name(),
                bound == null ? null : bound.framework(),
                employee.capabilities().stream().sorted().toList(),
                employee.dataScope(), employee.fileScope(), employee.endpoint(),
                employee.endpointApproved(), employee.lastHeartbeat());
    }

    private Map<String, Agent> agentMap() {
        Map<String, Agent> map = new LinkedHashMap<>();
        for (Agent agent : agents.listAll()) {
            map.put(agent.agentId(), agent);
        }
        return map;
    }

    private void requireStatus(Employee employee, String status, String message) {
        if (!status.equals(employee.status())) {
            throw ApiException.conflict("invalid_transition", message);
        }
    }

    private String issueSession(String employeeId, Instant now) {
        String token = ids.token();
        Instant expiresAt = now.plusSeconds(properties.sessionDays() * 86400L);
        jdbc.update("""
                INSERT INTO identity_sessions (token_hash, employee_id, issued_at, expires_at)
                VALUES (?, ?, ?, ?)
                """, Tokens.hash(token), employeeId, now.getEpochSecond(),
                expiresAt.getEpochSecond());
        return token;
    }

    private Set<String> completedSteps() {
        return new HashSet<>(jdbc.queryForList(
                "SELECT step FROM identity_bootstrap_steps", String.class));
    }

    private void markStep(String step, Map<String, Object> detail) {
        jdbc.update("""
                INSERT INTO identity_bootstrap_steps (step, detail, completed_at)
                VALUES (?, ?, ?)
                ON CONFLICT (step) DO UPDATE SET detail = excluded.detail,
                    completed_at = excluded.completed_at
                """, step, json(detail), Instant.now().getEpochSecond());
    }

    private Map<String, Object> stepDetail(String step) {
        List<String> rows = jdbc.queryForList(
                "SELECT detail FROM identity_bootstrap_steps WHERE step = ?", String.class, step);
        if (rows.isEmpty()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(rows.get(0), new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception exception) {
            return Map.of();
        }
    }

    private Invite invite(String code) {
        List<Invite> rows = jdbc.query("""
                SELECT * FROM identity_invites WHERE invite_code = ?
                """, (row, index) -> new Invite(
                row.getString("invite_code"), row.getString("account_type"),
                row.getString("team_id"), row.getString("position_id"),
                row.getString("data_scope"), caps(row.getString("capabilities")),
                nullableEpoch(row, "expires_at"), nullableEpoch(row, "consumed_at")), code);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.domain("invite_invalid", "邀请码不存在"));
    }

    private void validateInvite(Invite invite, String accountType, Instant now) {
        if (invite.consumedAt() != null) {
            throw ApiException.domain("invite_invalid", "邀请码已被使用");
        }
        if (invite.expiresAt() != null && !invite.expiresAt().isAfter(now)) {
            throw ApiException.domain("invite_invalid", "邀请码已过期");
        }
        if (!invite.accountType().equals(accountType)) {
            throw ApiException.domain("invite_invalid", "邀请码与账号类型不匹配");
        }
    }

    private Instant nullableEpoch(java.sql.ResultSet row, String column) throws java.sql.SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }

    private List<String> caps(String value) {
        try {
            return objectMapper.readValue(value == null ? "[]" : value,
                    new TypeReference<List<String>>() {
                    });
        } catch (Exception exception) {
            return List.of();
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            return "{}";
        }
    }

    private String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private record Invite(String inviteCode, String accountType, String teamId, String positionId,
                          String dataScope, List<String> capabilities, Instant expiresAt,
                          Instant consumedAt) {
    }
}
