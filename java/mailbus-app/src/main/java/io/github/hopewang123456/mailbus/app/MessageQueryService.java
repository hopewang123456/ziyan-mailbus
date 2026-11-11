package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.MessageProjection;
import io.github.hopewang123456.mailbus.ports.MessageProjection.MessageView;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * D16 批2：查询面切到 python SoT 投影（读 inbox.json，不读 java 独有文件/索引）。
 *
 * <p>返回形状逐字段对齐 python {@code handlers_inbox}：
 * {@code GET /api/inbox/{agent}} → {agent, has_unread, total, unread, messages[], truncated}；
 * {@code GET /api/replies} → {agent: [{id, from, type, content, status, state, created_at}]}。
 *
 * <p>python 的消息字段是宽松 JSON（state/status 双轨、pushed_count、attachments…），
 * 这里从投影的原始 map 取，缺省值与 python 直读一致。
 */
public class MessageQueryService {

    private final MessageProjection projection;

    public MessageQueryService(MessageProjection projection) {
        this.projection = projection;
    }

    /** python {@code handle_inbox}：status_filter 精确匹配 state，limit 按时间倒序截断。 */
    public Map<String, Object> inbox(String agent, String statusFilter, int limit) {
        List<MessageView> views = projection.messagesOf(agent);
        long unread = views.stream()
                .filter(v -> !v.record().state().isTerminal())
                .count();
        List<MessageView> source = new ArrayList<>(views);
        if (limit > 0 && (statusFilter == null || statusFilter.isBlank())) {
            source.sort(Comparator.comparing(MessageQueryService::createdRaw).reversed());
            if (source.size() > limit) {
                source = source.subList(0, limit);
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (MessageView v : source) {
            if (statusFilter != null && !statusFilter.isBlank() && !statusFilter.equals(stateOf(v))) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", v.record().id());
            row.put("from", v.record().fromAgent());
            row.put("type", v.record().type());
            row.put("priority", priorityOf(v));
            row.put("content", v.record().content());
            row.put("status", statusOf(v));
            row.put("state", stateOf(v));
            row.put("attachments", attachmentsOf(v));
            row.put("created_at", createdRaw(v));
            row.put("pushed_count", intOf(v, "pushed_count"));
            out.add(row);
        }
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("agent", agent);
        doc.put("has_unread", projection.hasUnread(agent));
        doc.put("total", views.size());
        doc.put("unread", unread);
        doc.put("messages", out);
        doc.put("truncated", limit > 0 && views.size() > out.size());
        return doc;
    }

    /** python {@code handle_replies}：type ∈ reply/forward/task_reply，按 agent 分组。 */
    public Map<String, Object> replies() {
        Map<String, Object> results = new LinkedHashMap<>();
        for (String agent : projection.agents()) {
            List<Map<String, Object>> rows = new ArrayList<>();
            for (MessageView v : projection.messagesOf(agent)) {
                String type = v.record().type() == null ? "" : v.record().type();
                if (!type.equals("reply") && !type.equals("forward") && !type.equals("task_reply")) {
                    continue;
                }
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("id", v.record().id());
                row.put("from", v.record().fromAgent());
                row.put("type", type);
                row.put("content", v.record().content());
                row.put("status", statusOf(v));
                row.put("state", stateOf(v));
                row.put("created_at", createdRaw(v));
                rows.add(row);
            }
            if (!rows.isEmpty()) {
                results.put(agent, rows);
            }
        }
        return results;
    }

    /** python {@code _count_unread}：非终态消息数。 */
    public long unread(String agent) {
        return projection.unreadCount(agent);
    }

    public Optional<MessageView> findById(String messageId) {
        return projection.findById(messageId);
    }

    // ── raw 字段读取（python 消息宽松 JSON）────────────────────────────

    private static String stateOf(MessageView v) {
        Object state = v.raw().get("state");
        if (state != null && !String.valueOf(state).isEmpty()) {
            return String.valueOf(state);
        }
        return statusOf(v);
    }

    private static String statusOf(MessageView v) {
        Object status = v.raw().get("status");
        if (status != null && !String.valueOf(status).isEmpty()) {
            return String.valueOf(status);
        }
        return v.record().state().name().toLowerCase();
    }

    private static String priorityOf(MessageView v) {
        Object prio = v.raw().get("priority");
        if (prio != null && !String.valueOf(prio).isEmpty()) {
            return String.valueOf(prio);
        }
        return v.record().priority().name().toLowerCase();
    }

    private static String createdRaw(MessageView v) {
        Object created = v.raw().get("created_at");
        if (created != null && !String.valueOf(created).isEmpty()) {
            return String.valueOf(created);
        }
        Object received = v.raw().get("received_at");
        if (received != null && !String.valueOf(received).isEmpty()) {
            return String.valueOf(received);
        }
        return v.record().createdAt() == null ? "" : v.record().createdAt().toString();
    }

    private static List<?> attachmentsOf(MessageView v) {
        return v.raw().get("attachments") instanceof List<?> l ? l : List.of();
    }

    private static int intOf(MessageView v, String key) {
        Object n = v.raw().get(key);
        if (n instanceof Number num) {
            return num.intValue();
        }
        try {
            return n == null ? 0 : Integer.parseInt(String.valueOf(n));
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
