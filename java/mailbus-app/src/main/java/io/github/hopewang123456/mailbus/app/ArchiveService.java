package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageInboxWriter;
import io.github.hopewang123456.mailbus.ports.MessageProjection;

import java.util.ArrayList;
import java.util.List;

/**
 * Settled-message lifecycle: DONE/ACKNOWLEDGED(settled)/CLOSED messages move to
 * the python archive backlog file, then leave the inbox.
 *
 * <p>D16 批3（D6）：归档格式对齐 python
 * {@code archive/<agent>/backlog-<stamp>.json}（{agent, archived_at, messages[]}），
 * 废弃 java {@code archive/<agent>/<date>/} 目录树。
 */
public class ArchiveService {

    public record Outcome(int archived, List<String> ids) {}

    private final MessageInboxWriter writer;
    private final MessageProjection projection;
    private final io.github.hopewang123456.mailbus.ports.MessageEventLog events;

    public ArchiveService(MessageInboxWriter writer, MessageProjection projection,
                          io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        this.writer = writer;
        this.projection = projection;
        this.events = events;
    }

    public Outcome archiveSettled(String agent) {
        // 归档前快照状态（事件流保持 from→ARCHIVED 的审计语义）
        java.util.Map<String, MessageState> before = new java.util.HashMap<>();
        for (var v : projection.messagesOf(agent)) {
            before.put(v.record().id(), v.record().state());
        }
        List<String> ids = writer.archiveSettled(agent);
        for (String id : ids) {
            MessageState from = before.getOrDefault(id, MessageState.DONE);
            events.append(id, agent, "archived", from.name(), MessageState.ARCHIVED.name(), "archive");
        }
        return new Outcome(ids.size(), ids);
    }

    /** trace: current snapshot + the full event stream (M2: typed events). */
    public List<String> trace(String messageId) {
        List<String> out = new ArrayList<>(projection.findById(messageId)
                .map(v -> {
                    MsgRecord r = v.record();
                    return List.of(
                            "id: " + r.id(),
                            "agent: " + r.toAgent() + "  from: " + r.fromAgent(),
                            "state: " + r.state(),
                            "created: " + r.createdAt() + "  updated: " + r.updatedAt(),
                            "content: " + (r.content().length() > 80
                                    ? r.content().substring(0, 80) + "..." : r.content()));
                })
                .orElseGet(() -> List.of("not found: " + messageId)));
        List<io.github.hopewang123456.mailbus.ports.MessageEventLog.Event> ev = events.eventsOf(messageId);
        if (!ev.isEmpty()) {
            out.add("events:");
            for (var e : ev) {
                out.add("  #" + e.seq() + " " + e.createdAt() + " " + e.kind() + " "
                        + (e.stateFrom() == null ? "-" : e.stateFrom()) + " -> " + e.stateTo()
                        + (e.detail().isBlank() ? "" : " (" + e.detail() + ")"));
            }
        }
        return out;
    }
}
