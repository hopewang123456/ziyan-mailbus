package io.github.hopewang123456.mailbus.dispatch;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.messaging.MessagingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * outbox 派发循环：与 Python Dispatcher 同语义。
 *
 * <p>claim due → 按 payload.channel 选通道 → 投递 → 记录消息尝试 → 标记 sent/failed/dead。
 * 单实例运行，不做跨进程抢占。</p>
 */
@Component
public class OutboxDispatcher {

    private static final Logger log = LoggerFactory.getLogger(OutboxDispatcher.class);
    private static final double MAX_BACKOFF_SEC = 60.0;

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final AppProperties properties;
    private final MessagingService messages;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).build();

    public OutboxDispatcher(JdbcTemplate jdbc, ObjectMapper objectMapper,
                            AppProperties properties, MessagingService messages) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.messages = messages;
    }

    public int tick() {
        List<Event> events = claimDue();
        for (Event event : events) {
            Delivery delivery;
            try {
                delivery = deliver(event);
            } catch (Exception exception) {
                String detail = exception.getMessage() == null
                        ? exception.getClass().getSimpleName() : exception.getMessage();
                delivery = new Delivery(false, "delivery_failed", truncate(detail));
            }
            if ("message.sent".equals(event.kind())) {
                Object messageId = event.payload().get("message_id");
                if (messageId != null) {
                    messages.recordDelivery(String.valueOf(messageId), delivery.ok(),
                            delivery.errorCode(), delivery.detail());
                }
            }
            if (delivery.ok()) {
                jdbc.update("UPDATE ops_outbox SET dispatched_at = ?, last_error = NULL"
                        + " WHERE event_id = ?", Instant.now().getEpochSecond(), event.eventId());
            } else if (event.attempts() + 1 >= properties.dispatchMaxAttempts()) {
                jdbc.update("UPDATE ops_outbox SET attempts = attempts + 1,"
                                + " dispatched_at = ?, last_error = ? WHERE event_id = ?",
                        Instant.now().getEpochSecond(),
                        delivery.errorCode() == null ? "delivery_failed" : delivery.errorCode(),
                        event.eventId());
            } else {
                int attempts = event.attempts() + 1;
                double nextDue = Instant.now().getEpochSecond()
                        + Math.min(Math.pow(2, attempts), MAX_BACKOFF_SEC);
                jdbc.update("UPDATE ops_outbox SET attempts = ?, due_at = ?, last_error = ?"
                                + " WHERE event_id = ?", attempts, nextDue,
                        delivery.errorCode() == null ? "delivery_failed" : delivery.errorCode(),
                        event.eventId());
            }
        }
        return events.size();
    }

    private List<Event> claimDue() {
        double now = Instant.now().getEpochSecond();
        return jdbc.query("""
                SELECT event_id, kind, payload, attempts FROM ops_outbox
                 WHERE dispatched_at IS NULL AND due_at <= ?
                 ORDER BY due_at LIMIT ?
                """, (row, index) -> new Event(row.getString("event_id"),
                row.getString("kind"), payload(row.getString("payload")),
                row.getInt("attempts")), now, properties.dispatchBatch());
    }

    private Delivery deliver(Event event) {
        Object channelValue = event.payload().get("channel");
        String channel = channelValue == null || String.valueOf(channelValue).isBlank()
                ? "file_bus" : String.valueOf(channelValue);
        String recipient = recipientOf(event);
        return switch (channel) {
            case "file_bus" -> stage(properties.fileBusDir()
                    .resolve("outbox").resolve(safeName(recipient)), event, "file_bus_written");
            case "mcp" -> stage(properties.mcpDir()
                    .resolve("pull").resolve(safeName(recipient)), event, "mcp_staged");
            case "a2a" -> deliverA2a(recipient, event);
            default -> new Delivery(false, "unknown_channel", channel);
        };
    }

    private Delivery stage(Path folder, Event event, String detail) {
        try {
            Files.createDirectories(folder);
            Path target = folder.resolve(safeName(event.eventId()) + ".json");
            Path temp = folder.resolve(safeName(event.eventId()) + ".tmp");
            Files.writeString(temp, objectMapper.writeValueAsString(document(event)),
                    StandardCharsets.UTF_8);
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
            return new Delivery(true, null, detail);
        } catch (Exception exception) {
            return new Delivery(false, "stage_failed", truncate(String.valueOf(
                    exception.getMessage())));
        }
    }

    private Delivery deliverA2a(String recipient, Event event) {
        List<String> endpoints = jdbc.query(
                "SELECT endpoint FROM identity_employees WHERE employee_id = ?",
                (row, index) -> row.getString("endpoint"), recipient);
        String endpoint = endpoints.isEmpty() ? null : endpoints.get(0);
        if (endpoint == null || endpoint.isBlank()) {
            return new Delivery(false, "endpoint_missing", null);
        }
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            objectMapper.writeValueAsString(document(event)),
                            StandardCharsets.UTF_8))
                    .build();
            HttpResponse<Void> response = http.send(request,
                    HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                return new Delivery(true, null, "a2a_delivered");
            }
            return new Delivery(false, "a2a_status", String.valueOf(response.statusCode()));
        } catch (Exception exception) {
            return new Delivery(false, "a2a_unreachable",
                    truncate(String.valueOf(exception.getMessage())));
        }
    }

    private Map<String, Object> document(Event event) {
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("event_id", event.eventId());
        document.put("kind", event.kind());
        document.put("payload", event.payload());
        document.put("attempts", event.attempts());
        return document;
    }

    private Map<String, Object> payload(String value) {
        try {
            Map<String, Object> data = objectMapper.readValue(value,
                    new TypeReference<Map<String, Object>>() {
                    });
            return data == null ? new LinkedHashMap<>() : data;
        } catch (Exception exception) {
            return new LinkedHashMap<>();
        }
    }

    private String recipientOf(Event event) {
        Object value = event.payload().get("recipient_id");
        String recipient = value == null ? "" : String.valueOf(value).strip();
        return recipient.isEmpty() ? "broadcast" : recipient;
    }

    static String safeName(String value) {
        String name = value.replaceAll("[^0-9A-Za-z_.-]+", "_");
        return name.isEmpty() ? "unknown" : name;
    }

    private String truncate(String value) {
        if (value == null) {
            return null;
        }
        return value.length() > 200 ? value.substring(0, 200) : value;
    }

    private record Event(String eventId, String kind, Map<String, Object> payload,
                         int attempts) {
    }

    private record Delivery(boolean ok, String errorCode, String detail) {
    }
}
