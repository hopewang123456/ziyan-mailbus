package io.github.hopewang123456.mailbus.auth;

import io.github.hopewang123456.mailbus.common.Tokens;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 不透明 Bearer token → Actor。HTTP 过滤器与 file_bus 入站共用。 */
@Component
public class TokenResolver {

    private final JdbcTemplate jdbc;

    public TokenResolver(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Actor resolve(String token) {
        if (token == null || token.isBlank()) {
            return null;
        }
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT e.employee_id, e.display_name, e.account_type, e.status, e.team_id,
                       e.data_scope, e.file_scope, e.endpoint_approved
                  FROM identity_sessions s
                  JOIN identity_employees e ON e.employee_id = s.employee_id
                 WHERE s.token_hash = ?
                   AND s.revoked_at IS NULL
                   AND (s.expires_at IS NULL OR s.expires_at > ?)
                   AND e.status <> 'deregistered'
                """, Tokens.hash(token), Instant.now().getEpochSecond());
        if (rows.isEmpty()) {
            return null;
        }
        Map<String, Object> row = rows.get(0);
        String employeeId = String.valueOf(row.get("employee_id"));
        Set<String> capabilities = new HashSet<>(jdbc.queryForList(
                "SELECT permission FROM identity_permission_grants WHERE employee_id = ?",
                String.class, employeeId));
        return new Actor(
                employeeId,
                String.valueOf(row.get("display_name")),
                String.valueOf(row.get("account_type")),
                String.valueOf(row.get("status")),
                row.get("team_id") == null ? null : String.valueOf(row.get("team_id")),
                String.valueOf(row.get("data_scope")),
                String.valueOf(row.get("file_scope")),
                ((Number) row.get("endpoint_approved")).intValue() == 1,
                capabilities
        );
    }
}
