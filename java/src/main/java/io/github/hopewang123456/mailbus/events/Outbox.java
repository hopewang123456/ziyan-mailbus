package io.github.hopewang123456.mailbus.events;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.common.Ids;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class Outbox {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final ObjectMapper objectMapper;

    public Outbox(JdbcTemplate jdbc, Ids ids, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.objectMapper = objectMapper;
    }

    public void enqueue(String kind, Map<String, Object> payload) {
        Map<String, Object> body = new LinkedHashMap<>(payload);
        body.putIfAbsent("at", Instant.now().toString());
        jdbc.update("""
                INSERT INTO ops_outbox (event_id, kind, payload, attempts, due_at, created_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                ids.next("evt"), kind, json(body),
                Instant.now().getEpochSecond(), Instant.now().getEpochSecond());
    }

    private String json(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("事件序列化失败", exception);
        }
    }
}
