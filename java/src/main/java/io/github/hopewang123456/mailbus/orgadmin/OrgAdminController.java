package io.github.hopewang123456.mailbus.orgadmin;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.identity.IdentityDtos;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.annotation.Validated;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
@Validated
public class OrgAdminController {

    private final EmployeeAdminService employees;
    private final StructureAdminService structure;
    private final RoleAdminService roles;
    private final InviteAdminService invites;

    public OrgAdminController(EmployeeAdminService employees, StructureAdminService structure,
                              RoleAdminService roles, InviteAdminService invites) {
        this.employees = employees;
        this.structure = structure;
        this.roles = roles;
        this.invites = invites;
    }

    // ---------- 员工 ----------

    @GetMapping("/employees")
    public OrgAdminDtos.EmployeeListOut listEmployees(
            @RequestParam(required = false) @Pattern(regexp = "human|agent") String type,
            @RequestParam(name = "position_id", required = false) String positionId,
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<IdentityDtos.EmployeeView> items = employees.views(type, positionId);
        return new OrgAdminDtos.EmployeeListOut(slice(items, limit, offset), items.size(),
                limit, offset);
    }

    @PostMapping("/employees/invite")
    public OrgAdminDtos.InviteOut invite(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgAdminDtos.EmployeeInviteIn input) {
        return invites.issue(actor, input);
    }

    @GetMapping("/employees/{employeeId}")
    public IdentityDtos.EmployeeView getEmployee(@PathVariable String employeeId) {
        return employees.get(employeeId);
    }

    @PatchMapping("/employees/{employeeId}")
    public IdentityDtos.EmployeeView updateEmployee(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String employeeId,
            @RequestBody Map<String, Object> changes) {
        return employees.update(actor, employeeId, changes);
    }

    @DeleteMapping("/employees/{employeeId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteEmployee(@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
                               @PathVariable String employeeId) {
        employees.delete(actor, employeeId);
    }

    @GetMapping("/employees/{employeeId}/permissions")
    public OrgAdminDtos.PermissionsOut permissions(@PathVariable String employeeId) {
        return new OrgAdminDtos.PermissionsOut(employeeId, employees.permissions(employeeId));
    }

    @PutMapping("/employees/{employeeId}/permissions")
    public OrgAdminDtos.PermissionsOut setPermissions(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String employeeId,
            @RequestBody OrgAdminDtos.PermissionsIn input) {
        return new OrgAdminDtos.PermissionsOut(employeeId,
                employees.setPermissions(actor, employeeId, input.permissions()));
    }

    @GetMapping("/employees/{employeeId}/roles")
    public OrgAdminDtos.RolesOut employeeRoles(@PathVariable String employeeId) {
        return new OrgAdminDtos.RolesOut(employeeId, employees.roles(employeeId));
    }

    @PutMapping("/employees/{employeeId}/roles")
    public OrgAdminDtos.RolesOut setEmployeeRoles(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String employeeId,
            @RequestBody OrgAdminDtos.RolesIn input) {
        return new OrgAdminDtos.RolesOut(employeeId,
                employees.setRoles(actor, employeeId, input.roleIds()));
    }

    @GetMapping("/employees/{employeeId}/capabilities")
    public OrgAdminDtos.CapabilitiesOut capabilities(@PathVariable String employeeId) {
        return new OrgAdminDtos.CapabilitiesOut(employeeId, employees.capabilities(employeeId));
    }

    @PutMapping("/employees/{employeeId}/capabilities")
    public OrgAdminDtos.CapabilitiesOut setCapabilities(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String employeeId,
            @RequestBody OrgAdminDtos.CapabilitiesIn input) {
        return new OrgAdminDtos.CapabilitiesOut(employeeId,
                employees.setCapabilities(actor, employeeId, input.capabilities()));
    }

    @GetMapping("/options/employees")
    public OrgAdminDtos.OptionListOut employeeOptions(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(name = "position_id", required = false) String positionId,
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.OptionOut> items = employees.options(actor, positionId);
        return new OrgAdminDtos.OptionListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    @GetMapping("/options/positions")
    public OrgAdminDtos.OptionListOut positionOptions(
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.OptionOut> items = structure.listPositions().stream()
                .map(position -> new OrgAdminDtos.OptionOut(position.positionId(),
                        position.name(), true)).toList();
        return new OrgAdminDtos.OptionListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    // ---------- 岗位 ----------

    @GetMapping("/positions")
    public OrgAdminDtos.PositionListOut listPositions(
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.PositionOut> items = structure.listPositions();
        return new OrgAdminDtos.PositionListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    @PostMapping("/positions")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgAdminDtos.PositionOut createPosition(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgAdminDtos.PositionIn input) {
        return structure.createPosition(actor, input.name(), input.capabilities());
    }

    @GetMapping("/positions/{positionId}")
    public OrgAdminDtos.PositionOut getPosition(@PathVariable String positionId) {
        return structure.getPosition(positionId);
    }

    @PatchMapping("/positions/{positionId}")
    public OrgAdminDtos.PositionOut updatePosition(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String positionId,
            @Valid @RequestBody OrgAdminDtos.PositionIn input) {
        return structure.updatePosition(actor, positionId, input.name(), input.capabilities());
    }

    @DeleteMapping("/positions/{positionId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deletePosition(@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
                               @PathVariable String positionId) {
        structure.deletePosition(actor, positionId);
    }

    @PutMapping("/positions/{positionId}/roles")
    public OrgAdminDtos.PositionOut bindPositionRoles(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String positionId,
            @RequestBody OrgAdminDtos.BindingIn input) {
        return structure.bindPositionRoles(actor, positionId, input.ids());
    }

    @PutMapping("/positions/{positionId}/employees")
    public OrgAdminDtos.PositionOut bindPositionEmployees(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String positionId,
            @RequestBody OrgAdminDtos.BindingIn input) {
        return structure.bindPositionEmployees(actor, positionId, input.ids());
    }

    // ---------- 团队 ----------

    @GetMapping("/teams")
    public OrgAdminDtos.TeamListOut listTeams(
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.TeamOut> items = structure.listTeams();
        return new OrgAdminDtos.TeamListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    @PostMapping("/teams")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgAdminDtos.TeamOut createTeam(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgAdminDtos.TeamIn input) {
        return structure.createTeam(actor, input.name(), input.leaderEmployeeId());
    }

    @PatchMapping("/teams/{teamId}")
    public OrgAdminDtos.TeamOut updateTeam(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String teamId,
            @Valid @RequestBody OrgAdminDtos.TeamIn input) {
        return structure.updateTeam(actor, teamId, input.name(), input.leaderEmployeeId());
    }

    @DeleteMapping("/teams/{teamId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteTeam(@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
                           @PathVariable String teamId) {
        structure.deleteTeam(actor, teamId);
    }

    @GetMapping("/teams/{teamId}/seats")
    public OrgAdminDtos.SeatListOut teamSeats(
            @PathVariable String teamId,
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.SeatOut> items = structure.listTeamSeats(teamId);
        return new OrgAdminDtos.SeatListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    @PutMapping("/seats/{seatId}/assign")
    public OrgAdminDtos.SeatOut assignSeat(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String seatId,
            @RequestBody OrgAdminDtos.SeatAssignIn input) {
        return structure.assignSeat(actor, seatId, input.employeeId(), input.teamId(),
                input.positionId());
    }

    // ---------- 角色 ----------

    @GetMapping("/roles")
    public OrgAdminDtos.RoleListOut listRoles(
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<OrgAdminDtos.RoleOut> items = roles.list().stream().map(this::roleOut).toList();
        return new OrgAdminDtos.RoleListOut(slice(items, limit, offset), items.size(), limit,
                offset);
    }

    @PostMapping("/roles")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgAdminDtos.RoleOut createRole(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OrgAdminDtos.RoleIn input) {
        return roleOut(roles.create(actor, input));
    }

    @PatchMapping("/roles/{roleId}")
    public OrgAdminDtos.RoleOut updateRole(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String roleId,
            @Valid @RequestBody OrgAdminDtos.RoleIn input) {
        return roleOut(roles.update(actor, roleId, input));
    }

    @DeleteMapping("/roles/{roleId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteRole(@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
                           @PathVariable String roleId) {
        roles.delete(actor, roleId);
    }

    @PutMapping("/roles/{roleId}/positions")
    public OrgAdminDtos.RoleOut bindRolePositions(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String roleId,
            @RequestBody OrgAdminDtos.BindingIn input) {
        return roleOut(roles.bindPositions(actor, roleId, input.ids()));
    }

    @PutMapping("/roles/{roleId}/employees")
    public OrgAdminDtos.RoleOut bindRoleEmployees(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String roleId,
            @RequestBody OrgAdminDtos.BindingIn input) {
        return roleOut(roles.bindEmployees(actor, roleId, input.ids()));
    }

    // ---------- 邀请 ----------

    @PostMapping("/invites/{inviteId}/revoke")
    public OrgAdminDtos.InviteOut revokeInvite(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String inviteId) {
        return invites.revoke(actor, inviteId);
    }

    @PostMapping("/invites/{inviteId}/resend")
    public OrgAdminDtos.InviteOut resendInvite(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String inviteId) {
        return invites.resend(actor, inviteId);
    }

    @PostMapping("/invites/accept")
    @ResponseStatus(HttpStatus.CREATED)
    public OrgAdminDtos.InviteAcceptOut acceptInvite(
            @Valid @RequestBody OrgAdminDtos.InviteAcceptIn input) {
        return invites.accept(input);
    }

    private OrgAdminDtos.RoleOut roleOut(RoleStore.RoleData role) {
        return new OrgAdminDtos.RoleOut(role.roleId(), role.name(),
                OrgAdminSupport.sorted(role.capabilities()), role.description(), role.enabled(),
                role.icon(), role.color(), role.createdAt(), role.updatedAt());
    }

    private static <T> List<T> slice(List<T> items, int limit, int offset) {
        int from = Math.min(offset, items.size());
        int to = Math.min(from + limit, items.size());
        return items.subList(from, to);
    }
}
