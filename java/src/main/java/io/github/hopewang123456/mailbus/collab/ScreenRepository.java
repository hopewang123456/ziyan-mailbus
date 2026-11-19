package io.github.hopewang123456.mailbus.collab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** 大屏登记表的持久化访问。 */
@Repository
public class ScreenRepository {

    private final JdbcTemplate jdbc;

    public ScreenRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Row> listAll() {
        return jdbc.query("SELECT * FROM collab_screens ORDER BY created_at, screen_id",
                (result, index) -> map(result));
    }

    public Optional<Row> get(String screenId) {
        return jdbc.query("SELECT * FROM collab_screens WHERE screen_id = ?",
                (result, index) -> map(result), screenId).stream().findFirst();
    }

    public void save(Row row) {
        jdbc.update("""
                INSERT INTO collab_screens
                    (screen_id, name, floor_id, seat_id, online, last_seen_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (screen_id) DO UPDATE SET
                    name = excluded.name, floor_id = excluded.floor_id,
                    seat_id = excluded.seat_id, online = excluded.online,
                    last_seen_at = excluded.last_seen_at
                """, row.screenId(), row.name(), row.floorId(), row.seatId(),
                row.online() ? 1 : 0, epoch(row.lastSeen()), epoch(row.createdAt()));
    }

    private Row map(java.sql.ResultSet result) throws java.sql.SQLException {
        return new Row(result.getString("screen_id"), result.getString("name"),
                result.getString("floor_id"), result.getString("seat_id"),
                result.getInt("online") == 1, instant(result, "last_seen_at"),
                instant(result, "created_at"));
    }

    private Instant instant(java.sql.ResultSet result, String column)
            throws java.sql.SQLException {
        double value = result.getDouble(column);
        return result.wasNull() ? null : Instant.ofEpochMilli((long) (value * 1000));
    }

    private Double epoch(Instant value) {
        return value == null ? null : value.toEpochMilli() / 1000.0;
    }

    public record Row(String screenId, String name, String floorId, String seatId,
                      boolean online, Instant lastSeen, Instant createdAt) {
    }
}
