package io.github.hopewang123456.mailbus.messaging;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class MessagingService {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final Outbox outbox;

    public MessagingService(JdbcTemplate jdbc, Ids ids, Outbox outbox) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.outbox = outbox;
    }

    @Transactional
    public MessageDtos.MessageOut send(Actor actor, MessageDtos.MessageIn input, String channel) {
        return send(actor, input, channel, null);
    }

    @Transactional
    public MessageDtos.MessageOut send(Actor actor, MessageDtos.MessageIn input, String channel,
                                       String pairId) {
        Authz.ensureAllowed(actor, Authz.MESSAGE_SEND,
                Authz.Resource.owned("message", actor.employeeId()));
        String body = input.body() == null ? "" : input.body().strip();
        if (body.isEmpty()) {
            throw ApiException.conflict("invalid_state", "消息内容不能为空");
        }
        if (body.length() > 4000) {
            throw ApiException.conflict("invalid_state", "消息内容不能超过 4000 个字符");
        }
        String kind = input.kind() == null || input.kind().isBlank() ? "note" : input.kind().strip();
        if (kind.length() > 32) {
            throw ApiException.conflict("invalid_state", "消息类型不合法");
        }
        String actualChannel = channel == null || channel.isBlank() ? "file_bus" : channel;
        Instant now = Instant.now();
        String messageId = ids.next("msg");
        String recipient = input.recipientId() == null || input.recipientId().isBlank()
                ? null : input.recipientId();
        jdbc.update("""
                INSERT INTO msg_messages
                    (message_id, sender_id, recipient_id, kind, body, created_at, channel, pair_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, messageId, actor.employeeId(), recipient, kind, body,
                now.getEpochSecond(), actualChannel,
                pairId == null || pairId.isBlank() ? null : pairId);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("message_id", messageId);
        payload.put("sender_id", actor.employeeId());
        payload.put("recipient_id", recipient);
        payload.put("channel", actualChannel);
        payload.put("pair_id", pairId == null || pairId.isBlank() ? null : pairId);
        outbox.enqueue("message.sent", payload);
        return new MessageDtos.MessageOut(messageId, actor.employeeId(), recipient, kind, body,
                now, null, pairId == null || pairId.isBlank() ? null : pairId);
    }

    public List<MessageDtos.MessageOut> inbox(Actor actor) {
        return jdbc.query("""
                SELECT * FROM msg_messages WHERE recipient_id = ? OR recipient_id IS NULL
                 ORDER BY created_at DESC, message_id DESC
                """, (row, index) -> map(row), actor.employeeId());
    }

    public List<MessageDtos.MessageOut> list(Actor actor, String agent, String status,
                                             String since, int limit) {
        String viewerId = actor.has(Authz.ALL) ? null : actor.employeeId();
        return query(viewerId, agent, status, since, null, false, limit);
    }

    public List<MessageDtos.MessageOut> listCollab(Actor actor, String pairId, int limit) {
        String viewerId = actor.has(Authz.ALL) ? null : actor.employeeId();
        return query(viewerId, null, null, null, pairId, true, limit);
    }

    public List<MessageDtos.MessageOut> listPublicCollab(String pairId, int limit) {
        return query(null, null, null, null, pairId, true, limit);
    }

    private List<MessageDtos.MessageOut> query(String viewerId, String agent, String status,
                                               String since, String pairId,
                                               boolean collabOnly, int limit) {
        List<Object> params = new ArrayList<>();
        StringBuilder sql = new StringBuilder("""
                SELECT m.*, COALESCE((SELECT CASE WHEN a.ok = 1 THEN 'delivered' ELSE 'failed' END
                  FROM msg_delivery_attempts a WHERE a.message_id = m.message_id
                  ORDER BY a.attempt_no DESC LIMIT 1), 'pending') AS delivery_status
                  FROM msg_messages m WHERE 1 = 1
                """);
        if (collabOnly) {
            sql.append(" AND m.pair_id IS NOT NULL");
        }
        if (pairId != null && !pairId.isBlank()) {
            sql.append(" AND m.pair_id = ?");
            params.add(pairId);
        }
        if (viewerId != null) {
            sql.append(" AND (m.sender_id = ? OR m.recipient_id = ? OR m.recipient_id IS NULL)");
            params.add(viewerId);
            params.add(viewerId);
        }
        if (agent != null && !agent.isBlank()) {
            sql.append(" AND (m.sender_id = ? OR m.recipient_id = ?)");
            params.add(agent);
            params.add(agent);
        }
        if (since != null && !since.isBlank()) {
            sql.append(" AND m.created_at >= ?");
            params.add(parseInstant(since).getEpochSecond());
        }
        if (status != null && !status.isBlank()) {
            String latest = "COALESCE((SELECT CASE WHEN a.ok = 1 THEN 'delivered' ELSE 'failed' END"
                    + " FROM msg_delivery_attempts a WHERE a.message_id = m.message_id"
                    + " ORDER BY a.attempt_no DESC LIMIT 1), 'pending')";
            sql.append(" AND ").append(latest).append(" = ?");
            params.add(status);
        }
        sql.append(" ORDER BY m.created_at DESC, m.message_id DESC LIMIT ?");
        params.add(Math.max(1, Math.min(limit, 500)));
        return jdbc.query(sql.toString(),
                (row, index) -> mapWithStatus(row), params.toArray());
    }

    public MessageDtos.MessageOut get(Actor actor, String messageId) {
        MessageDtos.MessageOut message = find(messageId);
        ensureReadable(actor, message);
        return message;
    }

    /** 删除消息：仅系统配置者可操作；投递尝试一并清理并留审计事件。 */
    @Transactional
    public void delete(Actor actor, String messageId) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        MessageDtos.MessageOut message = find(messageId);
        jdbc.update("DELETE FROM msg_delivery_attempts WHERE message_id = ?", messageId);
        jdbc.update("DELETE FROM msg_messages WHERE message_id = ?", messageId);
        outbox.enqueue("message.deleted", Map.of(
                "message_id", message.messageId(),
                "actor_id", actor.employeeId()));
    }

    public List<MessageDtos.DeliveryAttemptOut> attempts(Actor actor, String messageId) {
        MessageDtos.MessageOut message = find(messageId);
        ensureReadable(actor, message);
        return jdbc.query("""
                SELECT * FROM msg_delivery_attempts WHERE message_id = ? ORDER BY attempt_no
                """, (row, index) -> new MessageDtos.DeliveryAttemptOut(
                row.getString("message_id"), row.getInt("attempt_no"),
                row.getInt("ok") == 1, row.getString("error_code"), row.getString("detail"),
                Instant.ofEpochSecond((long) row.getDouble("at"))), messageId);
    }

    public List<MessageDtos.PullItem> pull(Actor actor) {
        return jdbc.query("""
                SELECT event_id, kind, payload, attempts FROM ops_outbox
                 WHERE dispatched_at IS NULL AND payload LIKE ?
                 ORDER BY created_at LIMIT 20
                """, (row, index) -> new MessageDtos.PullItem(
                row.getString("event_id"), row.getString("kind"),
                parsePayload(row.getString("payload")), row.getInt("attempts")),
                "%" + actor.employeeId() + "%");
    }

    /** 派发器回调：把 message.sent 的投递结果记入尝试表。 */
    public void recordDelivery(String messageId, boolean ok, String errorCode, String detail) {
        Integer exists = jdbc.queryForObject(
                "SELECT COUNT(*) FROM msg_messages WHERE message_id = ?",
                Integer.class, messageId);
        if (exists == null || exists == 0) {
            return;
        }
        Integer next = jdbc.queryForObject("""
                SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM msg_delivery_attempts
                 WHERE message_id = ?
                """, Integer.class, messageId);
        jdbc.update("""
                INSERT INTO msg_delivery_attempts
                    (message_id, attempt_no, ok, error_code, detail, at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, messageId, next == null ? 1 : next, ok ? 1 : 0, errorCode, detail,
                Instant.now().getEpochSecond());
    }

    private MessageDtos.MessageOut find(String messageId) {
        List<MessageDtos.MessageOut> rows = jdbc.query(
                "SELECT * FROM msg_messages WHERE message_id = ?",
                (row, index) -> map(row), messageId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("消息不存在"));
    }

    private void ensureReadable(Actor actor, MessageDtos.MessageOut message) {
        if (actor.has(Authz.ALL)) {
            return;
        }
        if (actor.employeeId().equals(message.senderId())
                || message.recipientId() == null
                || actor.employeeId().equals(message.recipientId())) {
            return;
        }
        throw ApiException.forbidden("无权查看该消息");
    }

    private MessageDtos.MessageOut map(java.sql.ResultSet row) throws java.sql.SQLException {
        return new MessageDtos.MessageOut(
                row.getString("message_id"), row.getString("sender_id"),
                row.getString("recipient_id"), row.getString("kind"), row.getString("body"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")), null,
                row.getString("pair_id"));
    }

    private MessageDtos.MessageOut mapWithStatus(java.sql.ResultSet row)
            throws java.sql.SQLException {
        return new MessageDtos.MessageOut(
                row.getString("message_id"), row.getString("sender_id"),
                row.getString("recipient_id"), row.getString("kind"), row.getString("body"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                row.getString("delivery_status"), row.getString("pair_id"));
    }

    private Instant parseInstant(String value) {
        try {
            return Instant.parse(value);
        } catch (Exception exception) {
            throw ApiException.unprocessable();
        }
    }

    private Map<String, Object> parsePayload(String value) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(value,
                    new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {
                    });
        } catch (Exception exception) {
            return Map.of();
        }
    }
}
