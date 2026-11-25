package io.github.hopewang123456.mailbus.identity;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

@Repository
public class EmployeeRepository {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public EmployeeRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public Optional<Employee> find(String employeeId) {
        List<Employee> rows = jdbc.query(
                "SELECT * FROM identity_employees WHERE employee_id = ? AND deleted_at IS NULL",
                rowMapper(false), employeeId);
        return rows.stream().findFirst().map(this::withCapabilities);
    }

    public List<Employee> listAll() {
        return jdbc.query(
                        "SELECT * FROM identity_employees WHERE deleted_at IS NULL"
                                + " ORDER BY created_at", rowMapper(false))
                .stream().map(this::withCapabilities).toList();
    }

    public Set<String> skills(String employeeId) {
        return new HashSet<>(jdbc.queryForList(
                "SELECT capability FROM employee_capabilities WHERE employee_id = ?",
                String.class, employeeId));
    }

    public void saveSkills(String employeeId, java.util.Collection<String> skills) {
        double now = Instant.now().getEpochSecond();
        jdbc.update("DELETE FROM employee_capabilities WHERE employee_id = ?", employeeId);
        for (String skill : new java.util.LinkedHashSet<>(skills)) {
            jdbc.update("""
                    INSERT OR IGNORE INTO employee_capabilities
                        (employee_id, capability, source, granted_at)
                    VALUES (?, ?, 'manual', ?)
                    """, employeeId, skill, now);
        }
    }

    private Employee withCapabilities(Employee employee) {
        Set<String> capabilities = new HashSet<>(jdbc.queryForList(
                "SELECT permission FROM identity_permission_grants WHERE employee_id = ?",
                String.class, employee.employeeId()));
        return new Employee(employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.positionId(), employee.seatId(),
                employee.agentId(), capabilities, employee.dataScope(), employee.fileScope(),
                employee.endpoint(), employee.endpointApproved(), employee.approvedAt(),
                employee.lastHeartbeat());
    }

    public void save(Employee employee) {
        double now = Instant.now().getEpochSecond();
        jdbc.update("""
                INSERT INTO identity_employees
                    (employee_id, display_name, account_type, status, team_id, position_id, seat_id,
                     agent_id, data_scope, file_scope, endpoint, endpoint_approved, approved_at,
                     last_heartbeat, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (employee_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    account_type = excluded.account_type,
                    status = excluded.status,
                    team_id = excluded.team_id,
                    position_id = excluded.position_id,
                    seat_id = excluded.seat_id,
                    agent_id = excluded.agent_id,
                    data_scope = excluded.data_scope,
                    file_scope = excluded.file_scope,
                    endpoint = excluded.endpoint,
                    endpoint_approved = excluded.endpoint_approved,
                    approved_at = excluded.approved_at,
                    last_heartbeat = excluded.last_heartbeat,
                    updated_at = excluded.updated_at
                """,
                employee.employeeId(), employee.displayName(), employee.accountType(),
                employee.status(), employee.teamId(), employee.positionId(), employee.seatId(),
                employee.agentId(), employee.dataScope(), json(employee.fileScope()),
                employee.endpoint(), employee.endpointApproved() ? 1 : 0,
                epoch(employee.approvedAt()), epoch(employee.lastHeartbeat()), now, now);
        jdbc.update("DELETE FROM identity_permission_grants WHERE employee_id = ?",
                employee.employeeId());
        for (String capability : employee.capabilities()) {
            jdbc.update("""
                    INSERT INTO identity_permission_grants (employee_id, permission, granted_at)
                    VALUES (?, ?, ?)
                    """, employee.employeeId(), capability, now);
        }
    }

    /** 员工仍有未结束的节点运行时拒绝移除。 */
    public int activeRunCount(String employeeId) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM task_node_runs
                 WHERE assigned_employee_id = ?
                   AND state NOT IN ('done', 'failed', 'skipped')
                """, Integer.class, employeeId);
        return count == null ? 0 : count;
    }

    public void softDelete(String employeeId, String actorId) {
        double now = Instant.now().getEpochSecond();
        jdbc.update("""
                UPDATE identity_employees SET deleted_at = ?, deleted_by = ?, updated_at = ?
                 WHERE employee_id = ? AND deleted_at IS NULL
                """, now, actorId, now, employeeId);
        jdbc.update("DELETE FROM employee_role_bindings WHERE employee_id = ?", employeeId);
        jdbc.update("DELETE FROM employee_capabilities WHERE employee_id = ?", employeeId);
    }

    public void clearTeamReference(String teamId) {
        jdbc.update("""
                UPDATE identity_employees SET team_id = NULL
                 WHERE team_id = ? AND (status = 'deregistered' OR deleted_at IS NOT NULL)
                """, teamId);
    }

    public void clearPositionReference(String positionId) {
        jdbc.update("""
                UPDATE identity_employees SET position_id = NULL
                 WHERE position_id = ? AND (status = 'deregistered' OR deleted_at IS NOT NULL)
                """, positionId);
    }

    /** 统计仍绑定该 Agent 的未注销员工数（用于 Agent 删除前的引用检查）。 */
    public int countActiveByAgent(String agentId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM identity_employees"
                        + " WHERE agent_id = ? AND status <> 'deregistered'",
                Integer.class, agentId);
        return count == null ? 0 : count;
    }

    public void revokeSessions(String employeeId) {
        jdbc.update("""
                UPDATE identity_sessions SET revoked_at = ?
                 WHERE employee_id = ? AND revoked_at IS NULL
                """, Instant.now().getEpochSecond(), employeeId);
    }

    private RowMapper<Employee> rowMapper(boolean ignored) {
        return (ResultSet row, int index) -> map(row);
    }

    private Employee map(ResultSet row) throws SQLException {
        String employeeId = row.getString("employee_id");
        return new Employee(
                employeeId,
                row.getString("display_name"),
                row.getString("account_type"),
                row.getString("status"),
                row.getString("team_id"),
                row.getString("position_id"),
                row.getString("seat_id"),
                row.getString("agent_id"),
                Set.of(),
                row.getString("data_scope"),
                fileScope(row.getString("file_scope")),
                row.getString("endpoint"),
                row.getInt("endpoint_approved") == 1,
                instant(row, "approved_at"),
                instant(row, "last_heartbeat")
        );
    }

    private List<String> fileScope(String value) {
        try {
            return objectMapper.readValue(value == null ? "[]" : value,
                    new TypeReference<List<String>>() {
                    });
        } catch (Exception exception) {
            return List.of();
        }
    }

    private String json(List<String> values) {
        try {
            return objectMapper.writeValueAsString(values);
        } catch (Exception exception) {
            return "[]";
        }
    }

    private Double epoch(Instant value) {
        return value == null ? null : (double) value.getEpochSecond();
    }

    private Instant instant(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }
}
