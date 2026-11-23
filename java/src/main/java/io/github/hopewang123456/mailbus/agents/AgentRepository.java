package io.github.hopewang123456.mailbus.agents;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

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
        return jdbc.query("SELECT * FROM agents ORDER BY created_at", this::map);
    }

    public Optional<Agent> find(String agentId) {
        return jdbc.query("SELECT * FROM agents WHERE agent_id = ?", this::map, agentId)
                .stream().findFirst();
    }

    public void delete(String agentId) {
        jdbc.update("DELETE FROM agents WHERE agent_id = ?", agentId);
    }

    public void save(Agent agent) {
        jdbc.update("""
                INSERT INTO agents
                    (agent_id, name, framework, model, endpoint, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (agent_id) DO UPDATE SET
                    name = excluded.name, framework = excluded.framework, model = excluded.model,
                    endpoint = excluded.endpoint, enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """, agent.agentId(), agent.name(), agent.framework(), agent.model(),
                agent.endpoint(), agent.enabled() ? 1 : 0,
                agent.createdAt().getEpochSecond(), agent.updatedAt().getEpochSecond());
    }

    private Agent map(java.sql.ResultSet row, int index) throws java.sql.SQLException {
        return new Agent(
                row.getString("agent_id"),
                row.getString("name"),
                row.getString("framework"),
                row.getString("model"),
                row.getString("endpoint"),
                row.getInt("enabled") == 1,
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                Instant.ofEpochSecond((long) row.getDouble("updated_at"))
        );
    }
}
