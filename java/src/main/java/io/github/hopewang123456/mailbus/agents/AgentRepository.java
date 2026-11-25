package io.github.hopewang123456.mailbus.agents;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public class AgentRepository {

    private final JdbcTemplate jdbc;

    public AgentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Agent> listAll() {
        return jdbc.query("SELECT * FROM agents WHERE deleted_at IS NULL"
                + " ORDER BY created_at, agent_id", this::map);
    }

    public Page listPage(int limit, int offset) {
        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM agents WHERE deleted_at IS NULL", Integer.class);
        List<Agent> items = jdbc.query("SELECT * FROM agents WHERE deleted_at IS NULL"
                + " ORDER BY created_at, agent_id LIMIT ? OFFSET ?", this::map, limit, offset);
        return new Page(items, total == null ? 0 : total);
    }

    public Optional<Agent> find(String agentId) {
        return jdbc.query("SELECT * FROM agents WHERE agent_id = ? AND deleted_at IS NULL",
                this::map, agentId).stream().findFirst();
    }

    public Optional<Agent> findByTokenLookup(String lookupHash) {
        double now = Instant.now().getEpochSecond();
        return jdbc.query("SELECT * FROM agents WHERE deleted_at IS NULL AND ("
                        + " endpoint_token_lookup_hash = ? OR (endpoint_token_prev_lookup_hash = ?"
                        + " AND (endpoint_token_prev_expires_at IS NULL"
                        + " OR endpoint_token_prev_expires_at > ?)))",
                this::map, lookupHash, lookupHash, now).stream().findFirst();
    }

    public void delete(String agentId) {
        jdbc.update("DELETE FROM agents WHERE agent_id = ?", agentId);
    }

    public void softDelete(String agentId, String actorId) {
        double now = Instant.now().getEpochSecond();
        jdbc.update("""
                UPDATE agents SET deleted_at = ?, deleted_by = ?, endpoint_token = NULL,
                    endpoint_token_lookup_hash = NULL, endpoint_token_prev = NULL,
                    endpoint_token_prev_lookup_hash = NULL,
                    endpoint_token_prev_expires_at = NULL, updated_at = ?
                 WHERE agent_id = ? AND deleted_at IS NULL
                """, now, actorId, now, agentId);
    }

    public void save(Agent agent) {
        jdbc.update("""
                INSERT INTO agents
                    (agent_id, name, framework, model, endpoint, enabled, agent_type,
                     channel_type, endpoint_token, endpoint_token_lookup_hash,
                     endpoint_token_prev, endpoint_token_prev_lookup_hash,
                     endpoint_token_prev_expires_at, last_seen_at, pending_endpoint,
                     endpoint_review_status, endpoint_approved_by, endpoint_approved_at,
                     deleted_at, deleted_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = excluded.name, framework = excluded.framework,
                    model = excluded.model, endpoint = excluded.endpoint,
                    enabled = excluded.enabled, agent_type = excluded.agent_type,
                    channel_type = excluded.channel_type,
                    endpoint_token = excluded.endpoint_token,
                    endpoint_token_lookup_hash = excluded.endpoint_token_lookup_hash,
                    endpoint_token_prev = excluded.endpoint_token_prev,
                    endpoint_token_prev_lookup_hash = excluded.endpoint_token_prev_lookup_hash,
                    endpoint_token_prev_expires_at = excluded.endpoint_token_prev_expires_at,
                    last_seen_at = excluded.last_seen_at,
                    pending_endpoint = excluded.pending_endpoint,
                    endpoint_review_status = excluded.endpoint_review_status,
                    endpoint_approved_by = excluded.endpoint_approved_by,
                    endpoint_approved_at = excluded.endpoint_approved_at,
                    deleted_at = excluded.deleted_at, deleted_by = excluded.deleted_by,
                    updated_at = excluded.updated_at
                """, agent.agentId(), agent.name(), agent.framework(), agent.model(),
                agent.endpoint(), agent.enabled() ? 1 : 0, agent.agentType(),
                agent.channelType(), agent.endpointToken(), agent.endpointTokenLookupHash(),
                agent.endpointTokenPrev(), agent.endpointTokenPrevLookupHash(),
                epoch(agent.endpointTokenPrevExpiresAt()), epoch(agent.lastSeenAt()),
                agent.pendingEndpoint(), agent.endpointReviewStatus(),
                agent.endpointApprovedBy(), epoch(agent.endpointApprovedAt()),
                epoch(agent.deletedAt()), agent.deletedBy(), epoch(agent.createdAt()),
                epoch(agent.updatedAt()));
    }

    // ---- 注册邀请码 ----

    public void addInvite(AgentInvite invite) {
        saveInvite(invite);
    }

    public void saveInvite(AgentInvite invite) {
        jdbc.update("""
                INSERT INTO agent_registration_invites
                    (invite_id, code_hash, employee_name, position_id, capabilities,
                     permissions, data_scope, agent_type, channel_type, expires_at,
                     created_by, created_at, used_by_agent_id, used_at, revoked_at, revoked_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (invite_id) DO UPDATE SET
                    used_by_agent_id = excluded.used_by_agent_id,
                    used_at = excluded.used_at, revoked_at = excluded.revoked_at,
                    revoked_by = excluded.revoked_by
                """, invite.inviteId(), invite.codeHash(), invite.employeeName(),
                invite.positionId(), json(invite.capabilities()), json(invite.permissions()),
                invite.dataScope(), invite.agentType(), invite.channelType(),
                epoch(invite.expiresAt()), invite.createdBy(),
                epoch(invite.createdAt() == null ? Instant.now() : invite.createdAt()),
                invite.usedByAgentId(), epoch(invite.usedAt()), epoch(invite.revokedAt()),
                invite.revokedBy());
    }

    public Optional<AgentInvite> findInvite(String inviteId) {
        return jdbc.query("SELECT * FROM agent_registration_invites WHERE invite_id = ?",
                this::mapInvite, inviteId).stream().findFirst();
    }

    public Optional<AgentInvite> findInviteByHash(String codeHash) {
        return jdbc.query("SELECT * FROM agent_registration_invites WHERE code_hash = ?",
                this::mapInvite, codeHash).stream().findFirst();
    }

    public InvitePage listInvites(int limit, int offset) {
        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM agent_registration_invites", Integer.class);
        List<AgentInvite> items = jdbc.query(
                "SELECT * FROM agent_registration_invites"
                        + " ORDER BY created_at DESC, invite_id LIMIT ? OFFSET ?",
                this::mapInvite, limit, offset);
        return new InvitePage(items, total == null ? 0 : total);
    }

    private Agent map(ResultSet row, int index) throws SQLException {
        return new Agent(
                row.getString("agent_id"),
                row.getString("name"),
                row.getString("framework"),
                row.getString("model"),
                row.getString("endpoint"),
                row.getInt("enabled") == 1,
                instant(row, "created_at"),
                instant(row, "updated_at"),
                text(row, "agent_type", "service"),
                text(row, "channel_type", "a2a"),
                row.getString("endpoint_token"),
                row.getString("endpoint_token_lookup_hash"),
                row.getString("endpoint_token_prev"),
                row.getString("endpoint_token_prev_lookup_hash"),
                instant(row, "endpoint_token_prev_expires_at"),
                instant(row, "last_seen_at"),
                row.getString("pending_endpoint"),
                text(row, "endpoint_review_status", "pending"),
                row.getString("endpoint_approved_by"),
                instant(row, "endpoint_approved_at"),
                instant(row, "deleted_at"),
                row.getString("deleted_by")
        );
    }

    private AgentInvite mapInvite(ResultSet row, int index) throws SQLException {
        return new AgentInvite(
                row.getString("invite_id"),
                row.getString("code_hash"),
                row.getString("employee_name"),
                row.getString("position_id"),
                list(row.getString("capabilities")),
                list(row.getString("permissions")),
                text(row, "data_scope", "self"),
                text(row, "agent_type", "external"),
                text(row, "channel_type", "a2a"),
                instant(row, "expires_at"),
                row.getString("created_by"),
                instant(row, "created_at"),
                row.getString("used_by_agent_id"),
                instant(row, "used_at"),
                instant(row, "revoked_at"),
                row.getString("revoked_by")
        );
    }

    private String text(ResultSet row, String column, String fallback) throws SQLException {
        String value = row.getString(column);
        return value == null || value.isBlank() ? fallback : value;
    }

    private Instant instant(ResultSet row, String column) throws SQLException {
        double value = row.getDouble(column);
        return row.wasNull() ? null : Instant.ofEpochSecond((long) value);
    }

    private Double epoch(Instant value) {
        return value == null ? null : (double) value.getEpochSecond();
    }

    private String json(List<String> values) {
        return "[" + String.join(",", values.stream()
                .map(value -> "\"" + value.replace("\"", "\\\"") + "\"")
                .toList()) + "]";
    }

    private List<String> list(String value) {
        if (value == null || value.isBlank() || "[]".equals(value)) {
            return List.of();
        }
        String body = value.trim();
        if (body.startsWith("[") && body.endsWith("]")) {
            body = body.substring(1, body.length() - 1);
        }
        if (body.isBlank()) {
            return List.of();
        }
        return java.util.Arrays.stream(body.split(","))
                .map(String::trim)
                .map(item -> item.replaceAll("^\"|\"$", ""))
                .filter(item -> !item.isBlank())
                .toList();
    }

    public record Page(List<Agent> items, int total) {
    }

    public record InvitePage(List<AgentInvite> items, int total) {
    }
}
