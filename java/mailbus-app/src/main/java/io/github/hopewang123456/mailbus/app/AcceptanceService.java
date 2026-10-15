package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Acceptance checks (python `mailbus acceptance` counterpart, first slice —
 * four of the eventual six): storage / scheduler heartbeat / patrol recency /
 * serve reachability (probed lazily; CLI runs report it as skipped).
 */
public class AcceptanceService {

    public record Item(String name, String status /* ok | warn | skip */, String detail) {}

    private final MessageRepository repository;
    private final MessageEventLog events;

    public AcceptanceService(MessageRepository repository, MessageEventLog events) {
        this.repository = repository;
        this.events = events;
    }

    public Map<String, Item> check() {
        Map<String, Item> items = new LinkedHashMap<>();
        items.put("storage", new Item("storage", "ok",
                "message index reachable, latest events=" + events.latest(1).size()));

        MessageEventLog.Heartbeat hb = events.heartbeatOf("patrol");
        if (hb == null) {
            items.put("scheduler", new Item("scheduler", "warn", "no heartbeat yet (serve not started?)"));
        } else {
            boolean ok = hb.ok();
            items.put("scheduler", new Item("scheduler", ok ? "ok" : "warn",
                    ok ? "last run " + hb.lastRunAt() : "last error: " + hb.error()));
        }

        // patrol recency: last event of any kind within 2x the patrol interval (default 5min)
        var last = events.latest(1);
        if (last.isEmpty()) {
            items.put("patrol", new Item("patrol", "warn", "no events yet"));
        } else {
            Duration age = Duration.between(Instant.parse(last.get(0).createdAt()), Instant.now());
            items.put("patrol", new Item("patrol", age.compareTo(Duration.ofMinutes(15)) < 0 ? "ok" : "warn",
                    "latest event " + age.toMinutes() + " min ago"));
        }

        items.put("serve_api", new Item("serve_api", "skip",
                "probe from CLI not wired yet — check http://<host>:9815/actuator/health"));
        return items;
    }

    public boolean allOk() {
        return check().values().stream().allMatch(i -> "ok".equals(i.status()));
    }
}
