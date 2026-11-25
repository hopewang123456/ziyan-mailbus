package io.github.hopewang123456.mailbus.orgadmin;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** 角色台账：增删改查与员工/岗位绑定。 */
@Service
public class RoleAdminService {

    private final RoleStore roles;
    private final EmployeeRepository employees;
    private final Ids ids;

    public RoleAdminService(RoleStore roles, EmployeeRepository employees, Ids ids) {
        this.roles = roles;
        this.employees = employees;
        this.ids = ids;
    }

    public List<RoleStore.RoleData> list() {
        return roles.listAll();
    }

    @Transactional
    public RoleStore.RoleData create(Actor actor, OrgAdminDtos.RoleIn input) {
        Authz.require(actor, Authz.ROLE_MANAGE);
        Instant now = Instant.now();
        RoleStore.RoleData role = role(ids.next("role"), input, now, now);
        roles.insert(role);
        return role;
    }

    @Transactional
    public RoleStore.RoleData update(Actor actor, String roleId, OrgAdminDtos.RoleIn input) {
        Authz.require(actor, Authz.ROLE_MANAGE);
        RoleStore.RoleData existing = load(roleId);
        RoleStore.RoleData role = role(roleId, input, existing.createdAt(), Instant.now());
        roles.update(role);
        return role;
    }

    @Transactional
    public void delete(Actor actor, String roleId) {
        Authz.require(actor, Authz.ROLE_MANAGE);
        load(roleId);
        if (!roles.employeeIds(roleId).isEmpty() || !roles.positionIds(roleId).isEmpty()) {
            throw ApiException.conflict("invalid_state", "角色仍被员工或岗位引用，请先解除绑定");
        }
        roles.delete(roleId);
    }

    @Transactional
    public RoleStore.RoleData bindPositions(Actor actor, String roleId, List<String> positionIds) {
        Authz.require(actor, Authz.ROLE_BIND);
        RoleStore.RoleData role = load(roleId);
        List<String> idsToBind = OrgAdminSupport.distinct(positionIds);
        roles.setPositions(roleId, idsToBind);
        return role;
    }

    @Transactional
    public RoleStore.RoleData bindEmployees(Actor actor, String roleId,
                                            List<String> employeeIds) {
        Authz.require(actor, Authz.ROLE_BIND);
        RoleStore.RoleData role = load(roleId);
        Set<String> known = new LinkedHashSet<>();
        for (Employee employee : employees.listAll()) {
            known.add(employee.employeeId());
        }
        for (String employeeId : employeeIds) {
            if (!known.contains(employeeId)) {
                throw ApiException.notFound("员工不存在：" + employeeId);
            }
        }
        roles.setEmployees(roleId, employeeIds);
        return role;
    }

    private RoleStore.RoleData load(String roleId) {
        return roles.find(roleId).orElseThrow(() -> ApiException.notFound("角色不存在"));
    }

    private RoleStore.RoleData role(String roleId, OrgAdminDtos.RoleIn input, Instant createdAt,
                                    Instant updatedAt) {
        return new RoleStore.RoleData(roleId, input.name(),
                new LinkedHashSet<>(OrgAdminSupport.cleanTags(input.capabilities())),
                input.description(), input.enabled() == null || input.enabled(),
                input.icon(), input.color(), createdAt, updatedAt);
    }
}
