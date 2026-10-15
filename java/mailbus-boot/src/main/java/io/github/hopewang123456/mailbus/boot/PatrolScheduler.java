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

    public PatrolScheduler(PatrolService patrol, MessageEventLog events) {
        this.patrol = patrol;
        this.events = events;
    }

    @Scheduled(fixedDelayString = "${mailbus.patrol.interval-ms:300000}", initialDelay = 10_000)
    public void patrolOnce() {
        try {
            patrol.patrol(Duration.ofMinutes(30), patrol.knownAgents());
            events.heartbeat("patrol", true, "");
        } catch (RuntimeException e) {
            events.heartbeat("patrol", false, String.valueOf(e.getMessage()));
        }
    }
}
