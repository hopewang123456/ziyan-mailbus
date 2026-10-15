package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.app.PatrolService;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * Scheduled patrol (python scheduler counterpart, first slice): every 5 min,
 * sweep stale PENDINGs and refresh the heartbeat the acceptance check reads.
 * Runs only in serve mode — the CLI dispatch path exits before schedules fire.
 */
@Component
public class PatrolScheduler {

    private final PatrolService patrol;
    private final MessageEventLog events;
    private final io.github.hopewang123456.mailbus.app.PushService push;

    public PatrolScheduler(PatrolService patrol, MessageEventLog events,
                           io.github.hopewang123456.mailbus.app.PushService push,
                           io.github.hopewang123456.mailbus.ports.AgentDirectory cards) {
        this.patrol = patrol;
        this.events = events;
        this.push = push;
        this.cards = cards;
    }

    @Scheduled(fixedDelayString = "${mailbus.patrol.interval-ms:300000}", initialDelay = 10_000)
    public void patrolOnce() {
        try {
            var report = patrol.patrol(Duration.ofMinutes(30), patrol.knownAgents());
            // scan/push loop: every enabled agent card gets its PENDINGs pushed
            int pushed = 0, failed = 0;
            for (var card : directoryCards()) {
                var pr = push.pushPending(card.id());
                pushed += pr.pushed();
                failed += pr.failed();
            }
            events.heartbeat("patrol", true,
                    "stale=" + report.staleCount() + " pushed=" + pushed + " pushFailed=" + failed);
        } catch (RuntimeException e) {
            events.heartbeat("patrol", false, String.valueOf(e.getMessage()));
        }
    }

    private java.util.List<io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard> directoryCards() {
        return cards.findAll().stream()
                .filter(io.github.hopewang123456.mailbus.ports.AgentDirectory.AgentCard::enabled)
                .toList();
    }

    private final io.github.hopewang123456.mailbus.ports.AgentDirectory cards;


}
