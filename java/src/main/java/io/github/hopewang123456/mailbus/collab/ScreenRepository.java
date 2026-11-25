package io.github.hopewang123456.mailbus.collab;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** 大屏登记表：只持久化密钥摘要与配置快照。 */
@Repository
public class ScreenRepository {

    private static final TypeReference<LinkedHashMap<String, Object>> MAP_TYPE =
            new TypeReference<>() {
            };

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public ScreenRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public List<Row> listPage(int limit, int offset) {
        return jdbc.query("""
                SELECT * FROM collab_screens
                 ORDER BY COALESCE(last_seen_at, created_at) DESC, screen_id
                 LIMIT ? OFFSET ?
                """, (result, index) -> map(result), limit, offset);
    }

    public int count() {
        Integer total = jdbc.queryForObject("SELECT COUNT(*) FROM collab_screens", Integer.class);
        return total == null ? 0 : total;
    }

    public List<Row> listAll() {
        return jdbc.query("""
                SELECT * FROM collab_screens
                 ORDER BY COALESCE(last_seen_at, created_at) DESC, screen_id
                """, (result, index) -> map(result));
    }

    public Optional<Row> get(String screenId) {
        return jdbc.query("SELECT * FROM collab_screens WHERE screen_id = ?",
                (result, index) -> map(result), screenId).stream().findFirst();
    }

    public void save(Row row) {
        jdbc.update("""
                INSERT INTO collab_screens
                    (screen_id, name, online, last_seen_at, created_at, secret_hash,
                     source, config_json, published_config_json, config_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (screen_id) DO UPDATE SET
                    name = excluded.name, online = excluded.online,
                    last_seen_at = excluded.last_seen_at,
                    secret_hash = excluded.secret_hash, source = excluded.source,
                    config_json = excluded.config_json,
                    published_config_json = excluded.published_config_json,
                    config_version = excluded.config_version,
                    updated_at = excluded.updated_at
                """, row.screenId(), row.name(), row.online() ? 1 : 0,
                epoch(row.lastSeen()), epoch(row.createdAt()), row.secretHash(),
                row.source(), json(row.config()), json(row.publishedConfig()),
                row.configVersion(), epoch(row.updatedAt()));
    }

    public void delete(String screenId) {
        jdbc.update("DELETE FROM collab_screens WHERE screen_id = ?", screenId);
    }

    private Row map(java.sql.ResultSet result) throws java.sql.SQLException {
        return new Row(result.getString("screen_id"), result.getString("name"),
                text(result, "source") == null ? "auto" : text(result, "source"),
                result.getInt("online") == 1, instant(result, "last_seen_at"),
                instant(result, "created_at"), map(result, "config_json"),
                map(result, "published_config_json"), integer(result, "config_version", 1),
                instant(result, "updated_at"), text(result, "secret_hash"));
    }

    private String text(java.sql.ResultSet result, String column) throws java.sql.SQLException {
        return result.getString(column);
    }

    private int integer(java.sql.ResultSet result, String column, int fallback)
            throws java.sql.SQLException {
        int value = result.getInt(column);
        return result.wasNull() ? fallback : value;
    }

    private Map<String, Object> map(java.sql.ResultSet result, String column)
            throws java.sql.SQLException {
        String raw = result.getString(column);
        if (raw == null || raw.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            return objectMapper.readValue(raw, MAP_TYPE);
        } catch (Exception exception) {
            return new LinkedHashMap<>();
        }
    }

    private String json(Map<String, Object> value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (Exception exception) {
            return "{}";
        }
    }

    private Instant instant(java.sql.ResultSet result, String column)
            throws java.sql.SQLException {
        double value = result.getDouble(column);
        return result.wasNull() ? null : Instant.ofEpochMilli((long) (value * 1000));
    }

    private Double epoch(Instant value) {
        return value == null ? null : value.toEpochMilli() / 1000.0;
    }

    public record Row(String screenId, String name, String source, boolean online,
                      Instant lastSeen, Instant createdAt, Map<String, Object> config,
                      Map<String, Object> publishedConfig, int configVersion,
                      Instant updatedAt, String secretHash) {
    }
}
