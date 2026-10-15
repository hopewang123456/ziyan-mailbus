package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageArchiver;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Settled-message lifecycle: DONE/ACKNOWLEDGED messages move to the archive
 * tree (file move + index state flip to ARCHIVED).
 */
public class ArchiveService {

    public record Outcome(int archived, List<String> ids) {}

    private final MessageRepository repository;
    private final MessageArchiver archiver;

    public ArchiveService(MessageRepository repository, MessageArchiver archiver) {
        this.repository = repository;
        this.archiver = archiver;
    }

    public Outcome archiveSettled(String agent) {
        List<String> ids = new ArrayList<>();
        for (MessageState settled : List.of(MessageState.DONE, MessageState.ACKNOWLEDGED)) {
            for (MsgRecord r : repository.findByAgentAndState(agent, settled)) {
                archiver.archive(r);
                repository.save(r.withState(MessageState.ARCHIVED, r.updatedAt()));
                ids.add(r.id());
            }
        }
        return new Outcome(ids.size(), ids);
    }

    /** trace: current state + timeline anchors (full event log arrives with M2 ApplicationEvents). */
    public List<String> trace(String messageId) {
        return repository.findById(messageId).map(r -> List.of(
                "id: " + r.id(),
                "agent: " + r.toAgent() + "  from: " + r.fromAgent(),
                "state: " + r.state(),
                "created: " + r.createdAt() + "  updated: " + r.updatedAt(),
                "content: " + (r.content().length() > 80 ? r.content().substring(0, 80) + "..." : r.content())
        )).orElseGet(() -> List.of("not found: " + messageId));
    }
}
