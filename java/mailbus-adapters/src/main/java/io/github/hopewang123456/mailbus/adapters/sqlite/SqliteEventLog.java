package io.github.hopewang123456.mailbus.adapters.sqlite;

import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.Clock;
import java.util.List;

/** msg_events / scheduler_state via JdbcTemplate (Flyway V3). */
public class SqliteEventLog implements MessageEventLog {

    private static final RowMapper<Event> MAPPER = (rs, i) -> new Event(
            rs.getLong("seq"), rs.getString("msg_id"), rs.getString("agent"),
            rs.getString("kind"), rs.getString("state_from"), rs.getString("state_to"),
            rs.getString("detail"), rs.getString("created_at"));

    private static final RowMapper<Heartbeat> HB = (rs, i) -> new Heartbeat(
            rs.getString("job"), rs.getString("last_run_at"),
            rs.getInt("last_ok") == 1, rs.getString("last_error"));

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public SqliteEventLog(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Override
    public void append(String msgId, String agent, String kind,
                       String stateFrom, String stateTo, String detail) {
        jdbc.update("INSERT INTO msg_events (msg_id, agent, kind, state_from, state_to, detail, created_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                msgId, agent, kind, stateFrom, stateTo, detail == null ? "" : detail,
                java.time.Instant.now(clock).toString());
    }

    @Override
    public List<Event> eventsOf(String msgId) {
        return jdbc.query("SELECT * FROM msg_events WHERE msg_id = ? ORDER BY seq", MAPPER, msgId);
    }

    @Override
    public List<Event> latest(int limit) {
        return jdbc.query("SELECT * FROM msg_events ORDER BY seq DESC LIMIT ?", MAPPER, limit);
    }

    @Override
    public void heartbeat(String job, boolean ok, String error) {
        jdbc.update("""
                INSERT INTO scheduler_state (id, job, last_run_at, last_ok, last_error)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  job = excluded.job,
                  last_run_at = excluded.last_run_at,
                  last_ok = excluded.last_ok,
                  last_error = excluded.last_error
                """, job, java.time.Instant.now(clock).toString(), ok ? 1 : 0, error == null ? "" : error);
    }

    @Override
    public Heartbeat heartbeatOf(String job) {
        List<Heartbeat> out = jdbc.query("SELECT * FROM scheduler_state WHERE id = 1", HB);
        return out.isEmpty() ? null : out.get(0);
    }
}
