package io.github.hopewang123456.mailbus.adapters.sqlite;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;

/**
 * SQLite-backed MessageRepository over the Flyway V1 msg_index table.
 *
 * Design note (plan §5): the message FILE is the source of truth; this table
 * is the index. The content column is a write-time snapshot so queries avoid
 * file IO — a reconcile pass (M2) re-syncs when files are hand-edited.
 * Schema lives in mailbus-boot db/migration/sqlite/V1__init.sql; the MySQL
 * twin follows the same columns (common-SQL-subset discipline).
 */
public class SqliteMessageRepository implements MessageRepository {

    private static final String UPSERT = """
            INSERT INTO msg_index (id, to_agent, from_agent, type, priority, state, file_path, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              state = excluded.state,
              updated_at = excluded.updated_at,
              priority = excluded.priority,
              content = excluded.content
            """;

    private static final RowMapper<MsgRecord> MAPPER = (ResultSet rs, int i) -> new MsgRecord(
            rs.getString("id"),
            rs.getString("to_agent"),
            rs.getString("from_agent"),
            rs.getString("type"),
            rs.getString("content") == null ? "" : contentOf(rs),
            MsgRecord.Priority.valueOf(rs.getString("priority")),
            MessageState.valueOf(rs.getString("state")),
            toInstant(rs, "created_at"),
            toInstant(rs, "updated_at"));

    private final JdbcTemplate jdbc;

    public SqliteMessageRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** content is a nullable snapshot column — kept out of the mapper hot path for clarity. */
    private static String contentOf(ResultSet rs) throws SQLException {
        return rs.getString("content");
    }

    /** created_at/updated_at are ISO-8601 UTC TEXT — explicit round-trip, no driver timezone. */
    private static Instant toInstant(ResultSet rs, String col) throws SQLException {
        String raw = rs.getString(col);
        return raw == null || raw.isBlank() ? Instant.EPOCH : Instant.parse(raw);
    }

    @Override
    public void save(MsgRecord r) {
        jdbc.update(UPSERT,
                r.id(), r.toAgent(), r.fromAgent(), r.type(),
                r.priority().name(), r.state().name(),
                filePathOf(r),
                r.content(),
                r.createdAt().toString(), r.updatedAt().toString());
    }

    @Override
    public java.util.Optional<MsgRecord> findById(String id) {
        List<MsgRecord> out = jdbc.query(
                "SELECT * FROM msg_index WHERE id = ?", MAPPER, id);
        return out.stream().findFirst();
    }

    @Override
    public List<MsgRecord> findByAgentAndState(String agent, MessageState state) {
        return jdbc.query(
                "SELECT * FROM msg_index WHERE to_agent = ? AND state = ? ORDER BY created_at",
                MAPPER, agent, state.name());
    }

    @Override
    public List<MsgRecord> findStalePending(String agent, Instant cutoff) {
        return jdbc.query(
                "SELECT * FROM msg_index WHERE to_agent = ? AND state = ? AND created_at < ? ORDER BY created_at",
                MAPPER, agent, MessageState.PENDING.name(), cutoff.toString());
    }

    @Override
    public long countUnread(String agent) {
        Long n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM msg_index WHERE to_agent = ? AND state NOT IN ('DONE','ACKNOWLEDGED','REJECTED','ARCHIVED')",
                Long.class, agent);
        return n == null ? 0 : n;
    }

    private static String filePathOf(MsgRecord r) {
        // Relative store path — files-as-SoT layout: inbox/<agent>/<id>.json
        return "inbox/" + r.toAgent() + "/" + r.id() + ".json";
    }
}
