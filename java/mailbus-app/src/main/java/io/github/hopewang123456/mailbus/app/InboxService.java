package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.infra.ids.Ids;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Inbox use case — send / ack / status surface for the CLI and API.
 * Zero framework deps (hexagonal app layer, mirrors the Python application
 * layer); wiring happens in mailbus-boot via @Bean. Clock injected
 * (the Python FakeClock lesson).
 */
public class InboxService {

    private final MessageRepository messages;
    private final Clock clock;

    public InboxService(MessageRepository messages, Clock clock) {
        this.messages = messages;
        this.clock = clock;
    }

    public MsgRecord send(String toAgent, String fromAgent, String content) {
        Instant now = Instant.now(clock);
        MsgRecord record = new MsgRecord(
                Ids.newMessageId(),
                toAgent, fromAgent, "notice", content,
                MsgRecord.Priority.NORMAL, MessageState.PENDING, now, now);
        messages.save(record);
        return record;
    }

    public Optional<MsgRecord> acknowledge(String messageId) {
        return messages.findById(messageId).map(r -> {
            MsgRecord acked = r.withState(MessageState.DONE, Instant.now(clock));
            messages.save(acked);
            return acked;
        });
    }

    public List<MsgRecord> inbox(String agent) {
        return messages.findByAgentAndState(agent, MessageState.PENDING);
    }

    public long unreadCount(String agent) {
        return messages.countUnread(agent);
    }
}
