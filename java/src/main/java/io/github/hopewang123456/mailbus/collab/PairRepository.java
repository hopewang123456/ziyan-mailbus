package io.github.hopewang123456.mailbus.collab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** 结对表的持久化访问。 */
@Repository
public class PairRepository {

    private final JdbcTemplate jdbc;

    public PairRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Row> list(String state, String viewerId, int limit) {
        List<Object> params = new ArrayList<>();
        StringBuilder sql = new StringBuilder("SELECT * FROM collab_pairs WHERE 1 = 1");
        if (state != null && !state.isBlank()) {
            sql.append(" AND state = ?");
            params.add(state);
        }
        if (viewerId != null) {
            sql.append(" AND (initiator_id = ? OR partner_id = ?)");
            params.add(viewerId);
            params.add(viewerId);
        }
        sql.append(" ORDER BY created_at DESC, pair_id DESC LIMIT ?");
        params.add(Math.max(1, Math.min(limit, 500)));
        return jdbc.query(sql.toString(), (row, index) -> map(row), params.toArray());
    }

    public Optional<Row> findActiveBetween(String leftId, String rightId) {
        return jdbc.query("""
                SELECT * FROM collab_pairs
                 WHERE state = 'active' AND ((initiator_id = ? AND partner_id = ?)
                    OR (initiator_id = ? AND partner_id = ?))
                 LIMIT 1
                """, (row, index) -> map(row), leftId, rightId, rightId, leftId)
                .stream().findFirst();
    }

    public Optional<Row> get(String pairId) {
        return jdbc.query("SELECT * FROM collab_pairs WHERE pair_id = ?",
                (row, index) -> map(row), pairId).stream().findFirst();
    }

    public void save(Row row) {
        jdbc.update("""
                INSERT INTO collab_pairs
                    (pair_id, initiator_id, partner_id, state, created_at, ended_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (pair_id) DO UPDATE SET
                    state = excluded.state, ended_at = excluded.ended_at
                """, row.pairId(), row.initiatorId(), row.partnerId(), row.state(),
                epoch(row.createdAt()), epoch(row.endedAt()));
    }

    private Row map(java.sql.ResultSet result) throws java.sql.SQLException {
        return new Row(result.getString("pair_id"), result.getString("initiator_id"),
                result.getString("partner_id"), result.getString("state"),
                instant(result, "created_at"), instant(result, "ended_at"));
    }

    private Instant instant(java.sql.ResultSet result, String column)
            throws java.sql.SQLException {
        double value = result.getDouble(column);
        return result.wasNull() ? null : Instant.ofEpochMilli((long) (value * 1000));
    }

    private Double epoch(Instant value) {
        return value == null ? null : value.toEpochMilli() / 1000.0;
    }

    public record Row(String pairId, String initiatorId, String partnerId, String state,
                      Instant createdAt, Instant endedAt) {
        public boolean involves(String employeeId) {
            return employeeId.equals(initiatorId) || employeeId.equals(partnerId);
        }
    }
}
