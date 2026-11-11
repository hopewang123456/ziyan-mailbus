package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.infra.ids.Ids;
import io.github.hopewang123456.mailbus.ports.MessageInboxWriter;
import io.github.hopewang123456.mailbus.ports.MessageProjection;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Inbox use case — send / ack / status surface for the CLI and API.
 * Zero framework deps (hexagonal app layer, mirrors the Python application
 * layer); wiring happens in mailbus-boot via @Bean. Clock injected
 * (the Python FakeClock lesson).
 *
 * <p>D16 批3：写路径落 python {@code inbox.json}（唯一 SoT），状态机与格式
 * 与 {@code file_bus.send / ack_handler.process_ack} 对齐；读路径走投影。
 */
public class InboxService {

    private final MessageInboxWriter writer;
    private final MessageProjection projection;
    private final io.github.hopewang123456.mailbus.ports.MessageEventLog events;
    private final Clock clock;

    public InboxService(MessageInboxWriter writer,
                        MessageProjection projection,
                        io.github.hopewang123456.mailbus.ports.MessageEventLog events,
                        Clock clock) {
        this.writer = writer;
        this.projection = projection;
        this.events = events;
        this.clock = clock;
    }

    public MsgRecord send(String toAgent, String fromAgent, String content) {
        return send(toAgent, fromAgent, content, "notice");
    }

    /** type=task/task_reply 时 ack 走 processing 两跳（python process_ack）。 */
    public MsgRecord send(String toAgent, String fromAgent, String content, String type) {
        Instant now = Instant.now(clock);
        MsgRecord record = new MsgRecord(
                Ids.newPythonMessageId(now), // python 格式 msg-YYYYMMDD-NNNNN
                toAgent, fromAgent, type, content,
                MsgRecord.Priority.NORMAL, MessageState.PENDING, now, now);
        writer.append(record);
        events.append(record.id(), toAgent, "created", null, MessageState.PENDING.name(), "send");
        return record;
    }

    /**
     * python ack 语义（见 ack_handler.process_ack）：task → processing，
     * 非 task → done；status 一律 acknowledged。java 事件流仍记录两跳视角。
     */
    public Optional<MsgRecord> acknowledge(String messageId) {
        return writer.acknowledge(messageId).map(r -> {
            events.append(r.id(), r.toAgent(), "state", MessageState.PENDING.name(),
                    r.state().name(), "ack");
            return r;
        });
    }

    /** python mark_read：仅置 status=acknowledged（不动状态机）。 */
    public List<String> markRead(String agent, List<String> messageIds) {
        return writer.markRead(agent, messageIds);
    }

    /** 待处理消息（PENDING 投影，供 CLI inbox 展示）。 */
    public List<MsgRecord> inbox(String agent) {
        return projection.messagesOf(agent).stream()
                .map(MessageProjection.MessageView::record)
                .filter(r -> r.state() == MessageState.PENDING)
                .toList();
    }

    public long unreadCount(String agent) {
        return projection.unreadCount(agent);
    }
}
