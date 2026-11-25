package io.github.hopewang123456.mailbus.orgadmin;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.identity.Employee;
import io.github.hopewang123456.mailbus.identity.EmployeeRepository;
import io.github.hopewang123456.mailbus.org.LayoutSeed;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 组织结构：团队、岗位与工位分配。 */
@Service
public class StructureAdminService {

    private record TeamData(String teamId, String name, String leaderEmployeeId,
                            Instant createdAt) {
    }

    private record PositionData(String positionId, String name, List<String> capabilities,
                                Instant createdAt) {
    }

    private record SeatOverride(String seatId, String teamId, String positionId,
                                Double x, Double y, Double rotation) {
    }

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final LayoutSeed seed;
    private final RoleStore roles;
    private final EmployeeRepository employees;
    private final ObjectMapper objectMapper;

    public StructureAdminService(JdbcTemplate jdbc, Ids ids, LayoutSeed seed, RoleStore roles,
                                 EmployeeRepository employees, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.seed = seed;
        this.roles = roles;
        this.employees = employees;
        this.objectMapper = objectMapper;
    }

    // ---------- 团队 ----------

    public List<OrgAdminDtos.TeamOut> listTeams() {
        return jdbc.query("SELECT * FROM org_teams ORDER BY created_at, team_id",
                (row, index) -> teamOut(new TeamData(row.getString("team_id"),
                        row.getString("name"), row.getString("leader_employee_id"),
                        OrgAdminSupport.instant(row, "created_at"))));
    }

    @Transactional
    public OrgAdminDtos.TeamOut createTeam(Actor actor, String name, String leaderEmployeeId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        ensureEmployee(leaderEmployeeId);
        String teamId = ids.next("team");
        Instant now = Instant.now();
        jdbc.update("""
                INSERT INTO org_teams (team_id, name, leader_employee_id, created_at)
                VALUES (?, ?, ?, ?)
                """, teamId, name, leaderEmployeeId, now.getEpochSecond());
        return teamOut(new TeamData(teamId, name, leaderEmployeeId, now));
    }

    @Transactional
    public OrgAdminDtos.TeamOut updateTeam(Actor actor, String teamId, String name,
                                           String leaderEmployeeId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        TeamData team = loadTeam(teamId);
        ensureEmployee(leaderEmployeeId);
        jdbc.update("UPDATE org_teams SET name = ?, leader_employee_id = ? WHERE team_id = ?",
                name, leaderEmployeeId, teamId);
        return teamOut(new TeamData(team.teamId(), name, leaderEmployeeId, team.createdAt()));
    }

    @Transactional
    public void deleteTeam(Actor actor, String teamId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        loadTeam(teamId);
        requireNoSeatReference("team_id", teamId, "团队仍被工位引用，请先解除工位归属");
        requireNoEmployeeReference("team_id", teamId, "团队仍被员工引用，请先调整员工归属");
        jdbc.update("""
                UPDATE identity_employees SET team_id = NULL
                 WHERE team_id = ? AND (status = 'deregistered' OR deleted_at IS NOT NULL)
                """, teamId);
        jdbc.update("DELETE FROM org_teams WHERE team_id = ?", teamId);
    }

    // ---------- 岗位 ----------

    public List<OrgAdminDtos.PositionOut> listPositions() {
        List<OrgAdminDtos.PositionOut> views = new ArrayList<>();
        for (PositionData position : jdbc.query("SELECT * FROM org_positions"
                + " ORDER BY created_at, position_id", (row, index) -> positionData(row))) {
            views.add(positionOut(position, roles.roleIdsForPosition(position.positionId())));
        }
        return views;
    }

    public OrgAdminDtos.PositionOut getPosition(String positionId) {
        PositionData position = loadPosition(positionId);
        return positionOut(position, roles.roleIdsForPosition(positionId));
    }

    @Transactional
    public OrgAdminDtos.PositionOut createPosition(Actor actor, String name,
                                                   List<String> capabilities) {
        Authz.require(actor, Authz.ORG_MANAGE);
        List<String> skills = OrgAdminSupport.requireTags(capabilities);
        String positionId = ids.next("pos");
        Instant now = Instant.now();
        jdbc.update("""
                INSERT INTO org_positions (position_id, name, capabilities, created_at)
                VALUES (?, ?, ?, ?)
                """, positionId, name, OrgAdminSupport.toJson(objectMapper, skills),
                now.getEpochSecond());
        return positionOut(new PositionData(positionId, name, skills, now), List.of());
    }

    @Transactional
    public OrgAdminDtos.PositionOut updatePosition(Actor actor, String positionId, String name,
                                                   List<String> capabilities) {
        Authz.require(actor, Authz.ORG_MANAGE);
        PositionData position = loadPosition(positionId);
        List<String> skills = OrgAdminSupport.requireTags(capabilities);
        jdbc.update("UPDATE org_positions SET name = ?, capabilities = ? WHERE position_id = ?",
                name, OrgAdminSupport.toJson(objectMapper, skills), positionId);
        return positionOut(new PositionData(positionId, name, skills, position.createdAt()),
                roles.roleIdsForPosition(positionId));
    }

    @Transactional
    public void deletePosition(Actor actor, String positionId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        loadPosition(positionId);
        requireNoSeatReference("position_id", positionId, "岗位仍被工位引用，请先解除工位归属");
        requireNoEmployeeReference("position_id", positionId, "岗位仍被员工引用，请先调整员工归属");
        jdbc.update("""
                UPDATE identity_employees SET position_id = NULL
                 WHERE position_id = ? AND (status = 'deregistered' OR deleted_at IS NOT NULL)
                """, positionId);
        jdbc.update("DELETE FROM position_role_bindings WHERE position_id = ?", positionId);
        jdbc.update("DELETE FROM org_positions WHERE position_id = ?", positionId);
    }

    @Transactional
    public OrgAdminDtos.PositionOut bindPositionRoles(Actor actor, String positionId,
                                                      List<String> roleIds) {
        Authz.require(actor, Authz.ROLE_BIND);
        PositionData position = loadPosition(positionId);
        ensureRoles(roleIds);
        roles.setRolesForPosition(positionId, roleIds);
        return positionOut(position, OrgAdminSupport.distinct(roleIds));
    }

    @Transactional
    public OrgAdminDtos.PositionOut bindPositionEmployees(Actor actor, String positionId,
                                                          List<String> employeeIds) {
        Authz.require(actor, Authz.ORG_MANAGE);
        PositionData position = loadPosition(positionId);
        List<Employee> all = employees.listAll();
        Map<String, Employee> targets = new LinkedHashMap<>();
        for (Employee employee : all) {
            targets.put(employee.employeeId(), employee);
        }
        for (String employeeId : employeeIds) {
            if (!targets.containsKey(employeeId)) {
                throw ApiException.notFound("员工不存在：" + employeeId);
            }
        }
        List<String> keep = OrgAdminSupport.distinct(employeeIds);
        for (Employee employee : all) {
            if (positionId.equals(employee.positionId()) && !keep.contains(employee.employeeId())) {
                employees.save(withPosition(employee, null));
            }
        }
        for (String employeeId : keep) {
            employees.save(withPosition(targets.get(employeeId), positionId));
            employees.saveSkills(employeeId, position.capabilities());
        }
        return positionOut(position, roles.roleIdsForPosition(positionId));
    }

    // ---------- 工位 ----------

    public List<OrgAdminDtos.SeatOut> listTeamSeats(String teamId) {
        loadTeam(teamId);
        Map<String, SeatOverride> overrides = overrides();
        Map<String, Employee> occupants = occupants();
        List<OrgAdminDtos.SeatOut> views = new ArrayList<>();
        for (LayoutSeed.Floor floor : seed.site().floors()) {
            for (LayoutSeed.Room room : floor.rooms()) {
                for (LayoutSeed.Seat seat : room.seats()) {
                    SeatOverride override = overrides.get(seat.seatId());
                    String effectiveTeam = override == null ? null : override.teamId();
                    if (!teamId.equals(effectiveTeam)) {
                        continue;
                    }
                    views.add(seatOut(seat, override, occupants.get(seat.seatId())));
                }
            }
        }
        return views;
    }

    @Transactional
    public OrgAdminDtos.SeatOut assignSeat(Actor actor, String seatId, String employeeId,
                                           String teamId, String positionId) {
        LayoutSeed.Seat seat = seed.site().seat(seatId)
                .orElseThrow(() -> ApiException.notFound("工位不存在"));
        Authz.require(actor, Authz.ORG_MANAGE);
        if (teamId != null) {
            loadTeam(teamId);
        }
        if (positionId != null) {
            loadPosition(positionId);
        }
        SeatOverride previous = overrides().get(seatId);
        SeatOverride assignment = new SeatOverride(seatId, teamId, positionId,
                previous == null ? null : previous.x(),
                previous == null ? null : previous.y(),
                previous == null ? null : previous.rotation());
        Employee occupant = assignOccupant(seatId, employeeId);
        jdbc.update("""
                INSERT INTO org_seats
                    (seat_id, team_id, position_id, x, y, rotation, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (seat_id) DO UPDATE SET
                    team_id = excluded.team_id, position_id = excluded.position_id,
                    x = excluded.x, y = excluded.y, rotation = excluded.rotation,
                    updated_at = excluded.updated_at
                """, seatId, teamId, positionId, assignment.x(), assignment.y(),
                assignment.rotation(), Instant.now().getEpochSecond());
        return seatOut(seat, assignment, occupant);
    }

    private Employee assignOccupant(String seatId, String employeeId) {
        Employee current = employees.listAll().stream()
                .filter(item -> seatId.equals(item.seatId()))
                .findFirst().orElse(null);
        if (employeeId == null) {
            if (current != null) {
                employees.save(withSeat(current, null));
            }
            return null;
        }
        Employee target = employees.find(employeeId)
                .orElseThrow(() -> ApiException.notFound("员工不存在"));
        if (current != null && !current.employeeId().equals(employeeId)) {
            throw ApiException.conflict("invalid_state", "工位已被占用");
        }
        employees.save(withSeat(target, seatId));
        return target;
    }

    // ---------- 辅助 ----------

    private TeamData loadTeam(String teamId) {
        return jdbc.query("SELECT * FROM org_teams WHERE team_id = ?",
                        (row, index) -> new TeamData(row.getString("team_id"),
                                row.getString("name"), row.getString("leader_employee_id"),
                                OrgAdminSupport.instant(row, "created_at")), teamId)
                .stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("团队不存在"));
    }

    private PositionData loadPosition(String positionId) {
        return jdbc.query("SELECT * FROM org_positions WHERE position_id = ?",
                        (row, index) -> positionData(row), positionId)
                .stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("岗位不存在"));
    }

    private PositionData positionData(java.sql.ResultSet row) throws java.sql.SQLException {
        return new PositionData(row.getString("position_id"), row.getString("name"),
                OrgAdminSupport.parseJsonArray(objectMapper, row.getString("capabilities")),
                OrgAdminSupport.instant(row, "created_at"));
    }

    private void ensureEmployee(String employeeId) {
        if (employeeId != null && employees.find(employeeId).isEmpty()) {
            throw ApiException.notFound("员工不存在");
        }
    }

    private void ensureRoles(List<String> roleIds) {
        for (String roleId : OrgAdminSupport.distinct(roleIds)) {
            if (roles.find(roleId).isEmpty()) {
                throw ApiException.notFound("角色不存在");
            }
        }
    }

    private void requireNoSeatReference(String column, String id, String message) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM org_seats WHERE " + column + " = ?", Integer.class, id);
        if (count != null && count > 0) {
            throw ApiException.conflict("invalid_state", message);
        }
    }

    private void requireNoEmployeeReference(String column, String id, String message) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM identity_employees WHERE "
                + column + " = ? AND status <> 'deregistered' AND deleted_at IS NULL",
                Integer.class, id);
        if (count != null && count > 0) {
            throw ApiException.conflict("invalid_state", message);
        }
    }

    private Map<String, SeatOverride> overrides() {
        Map<String, SeatOverride> map = new LinkedHashMap<>();
        for (SeatOverride override : jdbc.query("SELECT * FROM org_seats ORDER BY seat_id",
                (row, index) -> new SeatOverride(row.getString("seat_id"),
                        row.getString("team_id"), row.getString("position_id"),
                        OrgAdminSupport.boxedDouble(row, "x"),
                        OrgAdminSupport.boxedDouble(row, "y"),
                        OrgAdminSupport.boxedDouble(row, "rotation")))) {
            map.put(override.seatId(), override);
        }
        return map;
    }

    private Map<String, Employee> occupants() {
        Map<String, Employee> map = new LinkedHashMap<>();
        for (Employee employee : employees.listAll()) {
            if (employee.seatId() != null) {
                map.put(employee.seatId(), employee);
            }
        }
        return map;
    }

    private OrgAdminDtos.SeatOut seatOut(LayoutSeed.Seat seat, SeatOverride override,
                                         Employee occupant) {
        return new OrgAdminDtos.SeatOut(
                seat.seatId(),
                override == null ? null : override.teamId(),
                override == null ? null : override.positionId(),
                occupant == null ? null : occupant.employeeId(),
                occupant == null ? null : occupant.agentId(),
                override != null && override.x() != null ? override.x() : seat.x(),
                override != null && override.y() != null ? override.y() : seat.y(),
                override != null && override.rotation() != null
                        ? override.rotation() : seat.rotation());
    }

    private OrgAdminDtos.TeamOut teamOut(TeamData team) {
        return new OrgAdminDtos.TeamOut(team.teamId(), team.name(), team.leaderEmployeeId(),
                team.createdAt());
    }

    private OrgAdminDtos.PositionOut positionOut(PositionData position, List<String> roleIds) {
        return new OrgAdminDtos.PositionOut(position.positionId(), position.name(),
                OrgAdminSupport.sorted(position.capabilities()), roleIds, position.createdAt());
    }

    private Employee withPosition(Employee employee, String positionId) {
        return new Employee(employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), positionId, employee.seatId(),
                employee.agentId(), employee.capabilities(), employee.dataScope(),
                employee.fileScope(), employee.endpoint(), employee.endpointApproved(),
                employee.approvedAt(), employee.lastHeartbeat());
    }

    private Employee withSeat(Employee employee, String seatId) {
        return new Employee(employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.positionId(), seatId,
                employee.agentId(), employee.capabilities(), employee.dataScope(),
                employee.fileScope(), employee.endpoint(), employee.endpointApproved(),
                employee.approvedAt(), employee.lastHeartbeat());
    }
}
