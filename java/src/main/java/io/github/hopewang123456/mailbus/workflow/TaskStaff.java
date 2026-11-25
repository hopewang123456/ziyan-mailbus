package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.identity.Employee;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 派活候选与认领资格：岗位 → 角色 → 技能交集。 */
@Component
public class TaskStaff {

    private static final Set<String> ON_DUTY = Set.of("active", "offline");
    private static final long HEARTBEAT_TIMEOUT_SECONDS = 180;

    private final JdbcTemplate jdbc;
    private final TaskRepository tasks;
    private final ObjectMapper objectMapper;

    public TaskStaff(JdbcTemplate jdbc, TaskRepository tasks, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.tasks = tasks;
        this.objectMapper = objectMapper;
    }

    public List<Employee> pickCandidates(TaskGraph.GraphNode node, String accountType) {
        Set<String> required = requiredSkills(node);
        List<String> roleIds = roleIdsForPosition(node.positionId());
        List<Employee> candidates = new ArrayList<>();
        for (Employee employee : onDutyEmployees(accountType)) {
            if (!positionMatch(employee, node, roleIds)) {
                continue;
            }
            if (!required.isEmpty() && !intersects(skills(employee.employeeId()), required)) {
                continue;
            }
            if (!agentDispatchable(employee)) {
                continue;
            }
            candidates.add(employee);
        }
        candidates.sort((left, right) -> {
            int compare = Integer.compare(tasks.countActiveByEmployee(left.employeeId()),
                    tasks.countActiveByEmployee(right.employeeId()));
            return compare != 0 ? compare : left.employeeId().compareTo(right.employeeId());
        });
        return candidates;
    }

    public boolean canClaim(Employee employee, TaskGraph.GraphNode node) {
        if (employee == null || !"human".equals(employee.accountType())) {
            return false;
        }
        if (!ON_DUTY.contains(employee.status()) || deleted(employee.employeeId())) {
            return false;
        }
        if (node == null || node.positionId() == null || node.positionId().isBlank()) {
            return true;
        }
        return positionMatch(employee, node, roleIdsForPosition(node.positionId()));
    }

    private List<Employee> onDutyEmployees(String accountType) {
        return jdbc.query("""
                SELECT employee_id, display_name, account_type, status, team_id, position_id,
                       seat_id, agent_id, data_scope
                  FROM identity_employees
                 WHERE account_type = ? AND status IN ('active', 'offline')
                   AND deleted_at IS NULL
                 ORDER BY employee_id
                """, (row, index) -> new Employee(row.getString("employee_id"),
                row.getString("display_name"), row.getString("account_type"),
                row.getString("status"), row.getString("team_id"),
                row.getString("position_id"), row.getString("seat_id"),
                row.getString("agent_id"), Set.of(),
                row.getString("data_scope"), List.of(), null, false, null, null),
                accountType);
    }

    /** 端点待审批/被拒/离线/删除的 Agent 绝不派单；未登记台账的旧绑定保持兼容。 */
    private boolean agentDispatchable(Employee employee) {
        if (!"agent".equals(employee.accountType()) || employee.agentId() == null) {
            return true;
        }
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT endpoint, enabled, endpoint_review_status, last_seen_at, deleted_at"
                        + " FROM agents WHERE agent_id = ?", employee.agentId());
        if (rows.isEmpty()) {
            return true;
        }
        Map<String, Object> agent = rows.get(0);
        if (agent.get("deleted_at") != null || intValue(agent.get("enabled")) != 1) {
            return false;
        }
        if (!"approved".equals(text(agent.get("endpoint_review_status")))
                || text(agent.get("endpoint")) == null || text(agent.get("endpoint")).isBlank()) {
            return false;
        }
        Object seen = agent.get("last_seen_at");
        if (!(seen instanceof Number number)) {
            return false;
        }
        return Instant.now().getEpochSecond() - number.longValue() <= HEARTBEAT_TIMEOUT_SECONDS;
    }

    private boolean deleted(String employeeId) {
        Integer value = jdbc.queryForObject("SELECT COUNT(*) FROM identity_employees"
                + " WHERE employee_id = ? AND deleted_at IS NOT NULL", Integer.class, employeeId);
        return value != null && value > 0;
    }

    private boolean positionMatch(Employee employee, TaskGraph.GraphNode node,
                                  List<String> roleIds) {
        if (node.positionId() == null || node.positionId().isBlank()) {
            return true;
        }
        if (node.positionId().equals(employee.positionId())) {
            return true;
        }
        Set<String> employeeRoles = new HashSet<>(roleIdsForEmployee(employee.employeeId()));
        return employeeRoles.stream().anyMatch(roleIds::contains);
    }

    private Set<String> requiredSkills(TaskGraph.GraphNode node) {
        Set<String> skills = new LinkedHashSet<>();
        if (node.positionId() != null) {
            skills.addAll(jsonList(jdbc.queryForList(
                    "SELECT capabilities FROM org_positions WHERE position_id = ?",
                    String.class, node.positionId()).stream().findFirst().orElse(null)));
            for (String roleId : roleIdsForPosition(node.positionId())) {
                List<Map<String, Object>> rows = jdbc.queryForList(
                        "SELECT capabilities, enabled FROM agent_roles WHERE role_id = ?", roleId);
                if (!rows.isEmpty() && intValue(rows.get(0).get("enabled")) == 1) {
                    skills.addAll(jsonList(text(rows.get(0).get("capabilities"))));
                }
            }
        }
        return skills;
    }

    private Set<String> skills(String employeeId) {
        return new HashSet<>(jdbc.queryForList(
                "SELECT capability FROM employee_capabilities WHERE employee_id = ?",
                String.class, employeeId));
    }

    private List<String> roleIdsForPosition(String positionId) {
        if (positionId == null || positionId.isBlank()) {
            return List.of();
        }
        return jdbc.queryForList(
                "SELECT role_id FROM position_role_bindings WHERE position_id = ?",
                String.class, positionId);
    }

    private List<String> roleIdsForEmployee(String employeeId) {
        return jdbc.queryForList(
                "SELECT role_id FROM employee_role_bindings WHERE employee_id = ?",
                String.class, employeeId);
    }

    private Set<String> jsonList(String raw) {
        if (raw == null || raw.isBlank()) {
            return Set.of();
        }
        String trimmed = raw.trim();
        if (!trimmed.startsWith("[")) {
            return Set.of(trimmed);
        }
        try {
            List<String> values = objectMapper.readValue(trimmed,
                    new TypeReference<List<String>>() {
                    });
            return new LinkedHashSet<>(values);
        } catch (Exception exception) {
            return Set.of();
        }
    }

    private boolean intersects(Set<String> left, Set<String> right) {
        return left.stream().anyMatch(right::contains);
    }

    private String text(Object value) {
        return value == null ? null : value.toString();
    }

    private int intValue(Object value) {
        return value instanceof Number number ? number.intValue() : 0;
    }
}
