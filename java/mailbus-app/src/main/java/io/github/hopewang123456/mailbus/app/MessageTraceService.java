package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.MessageProjection;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * D16 批4：{@code /api/trace/{id}} 与 {@code /api/events} 转正实现。
 *
 * <p>消息快照来自统一 SoT（python inbox.json 投影），事件流来自 java
 * append-only {@code msg_events}（D4：java 侧语义增强，派生投影，允许重建期空洞）。
 * 消息不存在但仍有事件时仍返回事件（归档/清理后的追溯）。
 */
public class MessageTraceService {

    private final MessageProjection projection;
    private final MessageEventLog events;

    public MessageTraceService(MessageProjection projection, MessageEventLog events) {
        this.projection = projection;
        this.events = events;
    }

    /** 空 = 消息与事件都不存在（404）。 */
    public Optional<Map<String, Object>> trace(String messageId) {
        var found = projection.findById(messageId);
        List<Map<String, Object>> rows = toRows(events.eventsOf(messageId));
        if (found.isEmpty() && rows.isEmpty()) {
            return Optional.empty();
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "ok");
        body.put("message_id", messageId);
        body.put("found", found.isPresent());
        body.put("message", found.map(MessageTraceService::messageRow).orElse(null));
        body.put("events", rows);
        return Optional.of(body);
    }

    public Map<String, Object> recentEvents(int limit) {
        int n = Math.min(Math.max(limit, 1), 500);
        List<Map<String, Object>> rows = toRows(events.latest(n));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "ok");
        body.put("count", rows.size());
        body.put("events", rows);
        return body;
    }

    private static Map<String, Object> messageRow(MessageProjection.MessageView v) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", v.record().id());
        m.put("agent", v.agent());
        m.put("from", v.record().fromAgent());
        m.put("type", v.record().type());
        m.put("content", v.record().content());
        m.put("state", v.raw().getOrDefault("state", v.record().state().name().toLowerCase()));
        m.put("status", v.raw().getOrDefault("status", v.record().state().name().toLowerCase()));
        m.put("created_at", v.raw().getOrDefault("created_at", ""));
        return m;
    }

    private static List<Map<String, Object>> toRows(List<MessageEventLog.Event> list) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (MessageEventLog.Event e : list) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("seq", e.seq());
            row.put("msg_id", e.msgId());
            row.put("agent", e.agent());
            row.put("kind", e.kind());
            row.put("state_from", e.stateFrom());
            row.put("state_to", e.stateTo());
            row.put("detail", e.detail());
            row.put("created_at", e.createdAt());
            rows.add(row);
        }
        return rows;
    }
}
