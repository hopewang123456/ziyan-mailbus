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
                "SELECT * FROM identity_employees WHERE employee_id = ?",
                rowMapper(false), employeeId);
        return rows.stream().findFirst().map(this::withCapabilities);
    }

    public List<Employee> listAll() {
        return jdbc.query("SELECT * FROM identity_employees ORDER BY created_at",
                        rowMapper(false))
                .stream().map(this::withCapabilities).toList();
    }

    private Employee withCapabilities(Employee employee) {
        Set<String> capabilities = new HashSet<>(jdbc.queryForList(
                "SELECT capability FROM identity_capability_grants WHERE employee_id = ?",
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
        jdbc.update("DELETE FROM identity_capability_grants WHERE employee_id = ?",
                employee.employeeId());
        for (String capability : employee.capabilities()) {
            jdbc.update("""
                    INSERT INTO identity_capability_grants (employee_id, capability, granted_at)
                    VALUES (?, ?, ?)
                    """, employee.employeeId(), capability, now);
        }
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
