package io.github.hopewang123456.mailbus.orgadmin;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import io.github.hopewang123456.mailbus.identity.EmployeeViews;
import io.github.hopewang123456.mailbus.identity.IdentityDtos;
import io.github.hopewang123456.mailbus.org.LayoutSeed;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 员工目录：列表、详情、更新、软删除、权限/角色/技能与脱敏选项。 */
@Service
public class EmployeeAdminService {

    private final JdbcTemplate jdbc;
    private final EmployeeRepository employees;
    private final EmployeeViews views;
    private final RoleStore roles;
    private final LayoutSeed seed;
    private final ObjectMapper objectMapper;

    public EmployeeAdminService(JdbcTemplate jdbc, EmployeeRepository employees,
                                EmployeeViews views, RoleStore roles, LayoutSeed seed,
                                ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.employees = employees;
        this.views = views;
        this.roles = roles;
        this.seed = seed;
        this.objectMapper = objectMapper;
    }

    public List<Employee> list(String accountType, String positionId) {
        return employees.listAll().stream()
                .filter(item -> accountType == null || accountType.equals(item.accountType()))
                .filter(item -> positionId == null || positionId.equals(item.positionId()))
                .toList();
    }

    public List<IdentityDtos.EmployeeView> views(String accountType, String positionId) {
        return views.views(list(accountType, positionId));
    }

    public IdentityDtos.EmployeeView get(String employeeId) {
        return views.view(load(employeeId));
    }

    @Transactional
    public IdentityDtos.EmployeeView update(Actor actor, String employeeId,
                                            Map<String, Object> changes) {
        Employee target = load(employeeId);
        Authz.ensureAllowed(actor, Authz.ORG_MANAGE,
                new Authz.Resource("employee", null, target.teamId(), null));
        if ("deregistered".equals(target.status())) {
            throw ApiException.conflict("invalid_state", "已注销员工不能修改");
        }
        String displayName = target.displayName();
        String teamId = target.teamId();
        String positionId = target.positionId();
        String seatId = target.seatId();
        String dataScope = target.dataScope();
        List<String> skills = null;

        if (changes.containsKey("display_name") && changes.get("display_name") != null) {
            displayName = String.valueOf(changes.get("display_name"));
        }
        if (changes.containsKey("team_id")) {
            teamId = teamOrNull(changes.get("team_id"));
        }
        if (changes.containsKey("position_id")) {
            Object value = changes.get("position_id");
            if (value == null) {
                if ("agent".equals(target.accountType())) {
                    throw ApiException.unprocessable("unprocessable", "Agent 员工必须绑定岗位");
                }
                positionId = null;
            } else {
                positionId = String.valueOf(value);
                skills = positionSkills(positionId);
            }
        }
        if (changes.containsKey("seat_id")) {
            seatId = seatOrNull(changes.get("seat_id"), employeeId);
        }
        if (changes.get("data_scope") != null) {
            dataScope = String.valueOf(changes.get("data_scope"));
            if (!Set.of("self", "team", "global").contains(dataScope)) {
                throw ApiException.unprocessable("validation_error", "请求参数不合法");
            }
            OrgAdminSupport.ensureScopeGrantable(actor, dataScope);
        }
        boolean disable = changes.get("enabled") != null
                && !Boolean.TRUE.equals(changes.get("enabled"));
        boolean enable = changes.get("enabled") != null
                && Boolean.TRUE.equals(changes.get("enabled"));

        String status = target.status();
        if (disable) {
            status = "deregistered";
        } else if (enable) {
            if ("deregistered".equals(target.status())) {
                throw ApiException.conflict("invalid_state", "已停用员工不能直接启用，请重新邀请");
            }
            status = "active";
        }
        Employee updated = new Employee(target.employeeId(), displayName, target.accountType(),
                status, teamId, positionId, seatId, target.agentId(), target.capabilities(),
                dataScope, target.fileScope(), target.endpoint(), target.endpointApproved(),
                target.approvedAt(), target.lastHeartbeat());
        employees.save(updated);
        if (skills != null) {
            employees.saveSkills(employeeId, skills);
        }
        if ("deregistered".equals(status)) {
            employees.revokeSessions(employeeId);
        }
        return views.view(updated);
    }

    @Transactional
    public void delete(Actor actor, String employeeId) {
        Employee target = load(employeeId);
        Authz.ensureAllowed(actor, Authz.EMPLOYEE_REMOVE,
                new Authz.Resource("employee", target.employeeId(), target.teamId(), null));
        if (employees.activeRunCount(employeeId) > 0) {
            throw ApiException.conflict("invalid_state", "员工仍有进行中的任务，不能移除");
        }
        employees.softDelete(employeeId, actor.employeeId());
        employees.revokeSessions(employeeId);
    }

    public List<String> permissions(String employeeId) {
        return OrgAdminSupport.sorted(load(employeeId).capabilities());
    }

    @Transactional
    public List<String> setPermissions(Actor actor, String employeeId, List<String> values) {
        Employee target = load(employeeId);
        Authz.ensureAllowed(actor, Authz.CONSOLE_ADMIN,
                new Authz.Resource("employee", null, target.teamId(), null));
        Set<String> requested = OrgAdminSupport.parsePermissions(values);
        OrgAdminSupport.ensureGrantable(actor, requested, target.dataScope());
        Employee updated = new Employee(target.employeeId(), target.displayName(),
                target.accountType(), target.status(), target.teamId(), target.positionId(),
                target.seatId(), target.agentId(), requested, target.dataScope(),
                target.fileScope(), target.endpoint(), target.endpointApproved(),
                target.approvedAt(), target.lastHeartbeat());
        employees.save(updated);
        return OrgAdminSupport.sorted(requested);
    }

    public List<String> roles(String employeeId) {
        load(employeeId);
        return roles.roleIdsForEmployee(employeeId);
    }

    @Transactional
    public List<String> setRoles(Actor actor, String employeeId, List<String> roleIds) {
        Employee target = load(employeeId);
        Authz.ensureAllowed(actor, Authz.ROLE_BIND,
                new Authz.Resource("employee", null, target.teamId(), null));
        for (String roleId : OrgAdminSupport.distinct(roleIds)) {
            if (roles.find(roleId).isEmpty()) {
                throw ApiException.notFound("角色不存在：" + roleId);
            }
        }
        roles.setRolesForEmployee(employeeId, roleIds);
        return roles.roleIdsForEmployee(employeeId);
    }

    public List<String> capabilities(String employeeId) {
        load(employeeId);
        return OrgAdminSupport.sorted(employees.skills(employeeId));
    }

    @Transactional
    public List<String> setCapabilities(Actor actor, String employeeId, List<String> values) {
        Employee target = load(employeeId);
        Authz.ensureAllowed(actor, Authz.ROLE_BIND,
                new Authz.Resource("employee", null, target.teamId(), null));
        List<String> skills = OrgAdminSupport.requireEmployeeTags(values);
        employees.saveSkills(employeeId, skills);
        return OrgAdminSupport.sorted(skills);
    }

    public List<OrgAdminDtos.OptionOut> options(Actor actor, String positionId) {
        List<Employee> scoped = new ArrayList<>();
        for (Employee item : employees.listAll()) {
            boolean inScope = switch (actor.dataScope() == null ? "self" : actor.dataScope()) {
                case "global" -> true;
                case "team" -> actor.teamId() != null && actor.teamId().equals(item.teamId());
                default -> actor.employeeId().equals(item.employeeId());
            };
            if (inScope && (positionId == null || positionId.equals(item.positionId()))) {
                scoped.add(item);
            }
        }
        return scoped.stream()
                .map(item -> new OrgAdminDtos.OptionOut(item.employeeId(), item.displayName(),
                        !"pending".equals(item.status())
                                && !"deregistered".equals(item.status())))
                .toList();
    }

    private Employee load(String employeeId) {
        return employees.find(employeeId)
                .orElseThrow(() -> ApiException.notFound("员工不存在"));
    }

    private String teamOrNull(Object value) {
        if (value == null) {
            return null;
        }
        String teamId = String.valueOf(value);
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM org_teams WHERE team_id = ?", Integer.class, teamId);
        if (count == null || count == 0) {
            throw ApiException.notFound("团队不存在");
        }
        return teamId;
    }

    private String seatOrNull(Object value, String employeeId) {
        if (value == null) {
            return null;
        }
        String seatId = String.valueOf(value);
        if (!seed.site().hasSeat(seatId)) {
            throw ApiException.notFound("工位不存在");
        }
        Employee occupant = employees.listAll().stream()
                .filter(item -> seatId.equals(item.seatId()))
                .filter(item -> !item.employeeId().equals(employeeId))
                .findFirst().orElse(null);
        if (occupant != null) {
            throw ApiException.conflict("invalid_state", "工位已被占用");
        }
        return seatId;
    }

    private List<String> positionSkills(String positionId) {
        List<String> rows = jdbc.queryForList(
                "SELECT capabilities FROM org_positions WHERE position_id = ?",
                String.class, positionId);
        if (rows.isEmpty()) {
            throw ApiException.notFound("岗位不存在");
        }
        return OrgAdminSupport.parseJsonArray(objectMapper, rows.get(0));
    }
}
