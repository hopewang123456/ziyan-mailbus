package io.github.hopewang123456.mailbus.orgadmin;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** 角色台账与双向绑定的 SQLite 访问。 */
@Component
public class RoleStore {

    public record RoleData(String roleId, String name, Set<String> capabilities,
                           String description, boolean enabled, String icon, String color,
                           Instant createdAt, Instant updatedAt) {
    }

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public RoleStore(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public Optional<RoleData> find(String roleId) {
        return jdbc.query("SELECT * FROM agent_roles WHERE role_id = ?", this::map, roleId)
                .stream().findFirst();
    }

    public List<RoleData> listAll() {
        return jdbc.query("SELECT * FROM agent_roles ORDER BY created_at, role_id", this::map);
    }

    public void insert(RoleData role) {
        jdbc.update("""
                INSERT INTO agent_roles
                    (role_id, role_name, capabilities, description, enabled, icon, color,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, role.roleId(), role.name(),
                OrgAdminSupport.toJson(objectMapper, OrgAdminSupport.sorted(role.capabilities())),
                role.description(), role.enabled() ? 1 : 0, role.icon(), role.color(),
                role.createdAt().getEpochSecond(), role.updatedAt().getEpochSecond());
    }

    public void update(RoleData role) {
        jdbc.update("""
                UPDATE agent_roles SET role_name = ?, capabilities = ?, description = ?,
                    enabled = ?, icon = ?, color = ?, updated_at = ?
                 WHERE role_id = ?
                """, role.name(),
                OrgAdminSupport.toJson(objectMapper, OrgAdminSupport.sorted(role.capabilities())),
                role.description(), role.enabled() ? 1 : 0, role.icon(), role.color(),
                role.updatedAt().getEpochSecond(), role.roleId());
    }

    public void delete(String roleId) {
        jdbc.update("DELETE FROM agent_roles WHERE role_id = ?", roleId);
        jdbc.update("DELETE FROM employee_role_bindings WHERE role_id = ?", roleId);
        jdbc.update("DELETE FROM position_role_bindings WHERE role_id = ?", roleId);
    }

    public List<String> positionIds(String roleId) {
        return ids("position_role_bindings", "position_id", "role_id", roleId);
    }

    public List<String> employeeIds(String roleId) {
        return ids("employee_role_bindings", "employee_id", "role_id", roleId);
    }

    public void setPositions(String roleId, List<String> positionIds) {
        replace("position_role_bindings", "role_id", roleId, "position_id", positionIds);
    }

    public void setEmployees(String roleId, List<String> employeeIds) {
        replace("employee_role_bindings", "role_id", roleId, "employee_id", employeeIds);
    }

    public List<String> roleIdsForPosition(String positionId) {
        return ids("position_role_bindings", "role_id", "position_id", positionId);
    }

    public List<String> roleIdsForEmployee(String employeeId) {
        return ids("employee_role_bindings", "role_id", "employee_id", employeeId);
    }

    public void setRolesForPosition(String positionId, List<String> roleIds) {
        replace("position_role_bindings", "position_id", positionId, "role_id", roleIds);
    }

    public void setRolesForEmployee(String employeeId, List<String> roleIds) {
        replace("employee_role_bindings", "employee_id", employeeId, "role_id", roleIds);
    }

    private List<String> ids(String table, String column, String key, String value) {
        return jdbc.queryForList(
                "SELECT " + column + " FROM " + table + " WHERE " + key + " = ? ORDER BY " + column,
                String.class, value);
    }

    private void replace(String table, String key, String value, String column,
                         List<String> targets) {
        jdbc.update("DELETE FROM " + table + " WHERE " + key + " = ?", value);
        for (String target : OrgAdminSupport.distinct(targets)) {
            jdbc.update("INSERT OR IGNORE INTO " + table + " (" + key + ", " + column
                    + ") VALUES (?, ?)", value, target);
        }
    }

    private RoleData map(java.sql.ResultSet row, int index) throws java.sql.SQLException {
        return new RoleData(
                row.getString("role_id"),
                row.getString("role_name"),
                new java.util.LinkedHashSet<>(OrgAdminSupport.parseJsonArray(objectMapper,
                        row.getString("capabilities"))),
                row.getString("description"),
                row.getInt("enabled") == 1,
                row.getString("icon"),
                row.getString("color"),
                OrgAdminSupport.instant(row, "created_at"),
                OrgAdminSupport.instant(row, "updated_at"));
    }
}
