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
    private final io.github.hopewang123456.mailbus.ports.MessageEventLog events;

    public ArchiveService(MessageRepository repository, MessageArchiver archiver,
                          io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        this.repository = repository;
        this.archiver = archiver;
        this.events = events;
    }

    public Outcome archiveSettled(String agent) {
        List<String> ids = new ArrayList<>();
        for (MessageState settled : List.of(MessageState.DONE, MessageState.ACKNOWLEDGED)) {
            for (MsgRecord r : repository.findByAgentAndState(agent, settled)) {
                archiver.archive(r);
                repository.save(r.withState(MessageState.ARCHIVED, r.updatedAt()));
                events.append(r.id(), r.toAgent(), "archived", r.state().name(),
                        MessageState.ARCHIVED.name(), "archive");
                ids.add(r.id());
            }
        }
        return new Outcome(ids.size(), ids);
    }

    /** trace: current snapshot + the full event stream (M2: typed events). */
    public List<String> trace(String messageId) {
        List<String> out = new ArrayList<>(repository.findById(messageId)
                .map(r -> List.of(
                        "id: " + r.id(),
                        "agent: " + r.toAgent() + "  from: " + r.fromAgent(),
                        "state: " + r.state(),
                        "created: " + r.createdAt() + "  updated: " + r.updatedAt(),
                        "content: " + (r.content().length() > 80 ? r.content().substring(0, 80) + "..." : r.content())))
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
