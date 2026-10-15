package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.Notifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Daily digest job (python daily report counterpart, minimal slice): one
 * 09:00 summary line per day into the notify channels (file digest keeps
 * the human-readable daily trail).
 */
@Component
public class DigestScheduler {

    private final MessageEventLog events;
    private final Notifier notifier;

    public DigestScheduler(MessageEventLog events, Notifier notifier) {
        this.events = events;
        this.notifier = notifier;
    }

    @Scheduled(cron = "${mailbus.digest.cron:0 0 9 * * *}", zone = "UTC")
    public void dailyDigest() {
        var recent = events.latest(1000);
        notifier.notify(Notifier.Level.INFO, "daily digest",
                recent.size() + " recent events; latest "
                        + (recent.isEmpty() ? "none" : recent.get(0).kind() + " " + recent.get(0).createdAt()));
    }
}
