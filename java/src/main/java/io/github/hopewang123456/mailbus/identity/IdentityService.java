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
            // 从未报告在勤（外部导入等）与持全量权限的运维入口不参与巡检，
            // 避免被误标离线污染总览与审计。
            if (employee.lastHeartbeat() == null
                    || employee.capabilities().contains("*")) {
                continue;
            }
            if (employee.lastHeartbeat().getEpochSecond() >= cutoffEpochSeconds) {
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
}
