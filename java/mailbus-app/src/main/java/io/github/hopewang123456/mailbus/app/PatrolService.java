package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

/**
 * Patrol sweep (python `scan`/`patrol` counterpart, first slice): stale
 * PENDING detection + agent census. Runs on a schedule from boot; appends
 * patrol_stale events and keeps the scheduler heartbeat current — the data
 * the acceptance check reads.
 */
public class PatrolService {

    public record PatrolReport(int staleCount, List<String> agents) {}

    private final MessageRepository repository;
    private final MessageEventLog events;
    private final io.github.hopewang123456.mailbus.ports.Notifier notifier;

    public PatrolService(MessageRepository repository, MessageEventLog events,
                         io.github.hopewang123456.mailbus.ports.Notifier notifier) {
        this.repository = repository;
        this.events = events;
        this.notifier = notifier;
    }

    public PatrolReport patrol(Duration staleAfter, Iterable<String> agents) {
        Instant cutoff = Instant.now().minus(staleAfter);
        int stale = 0;
        List<String> roster = new ArrayList<>();
        for (String agent : agents) {
            roster.add(agent);
            for (var m : repository.findStalePending(agent, cutoff)) {
                events.append(m.id(), agent, "patrol_stale", MessageState.PENDING.name(),
                        MessageState.PENDING.name(), "pending beyond " + staleAfter);
                stale++;
            }
        }
        notifier.notify(io.github.hopewang123456.mailbus.ports.Notifier.Level.INFO,
                "patrol digest", "stale=" + stale + " agents=" + roster.size());
        if (stale > 0) {
            notifier.notify(io.github.hopewang123456.mailbus.ports.Notifier.Level.WARN,
                    "patrol stale", stale + " message(s) pending beyond threshold");
        }
        return new PatrolReport(stale, roster);
    }

    /** Agent census derived from the event stream (M2 grows a proper agents
     *  table with the lifecycle/workflow ports). */
    public List<String> knownAgents() {
        TreeSet<String> names = new TreeSet<>();
        for (var e : events.latest(500)) {
            names.add(e.agent());
        }
        return new ArrayList<>(names);
    }
}
