package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.AcceptanceService;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.PatrolService;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * Ops surface (M2): agents census, trace stream, acceptance, recent events,
 * inbox archive. All thin — every controller delegates to app services.
 */
@RestController
public class OpsController {

    private final PatrolService patrol;
    private final ArchiveService archive;
    private final AcceptanceService acceptance;
    private final InboxService inbox;
    private final MessageEventLog events;
    private final io.github.hopewang123456.mailbus.app.StatusService status;

    public OpsController(PatrolService patrol, ArchiveService archive,
                         AcceptanceService acceptance, InboxService inbox,
                         MessageEventLog events,
                         io.github.hopewang123456.mailbus.app.StatusService status) {
        this.patrol = patrol;
        this.archive = archive;
        this.acceptance = acceptance;
        this.inbox = inbox;
        this.events = events;
        this.status = status;
    }

    @GetMapping("/api/status")
    public Map<String, Object> status() {
        return status.status();
    }

    @GetMapping("/api/stats")
    public Map<String, Object> stats() {
        return status.stats();
    }

    @GetMapping("/api/agents")
    public Map<String, Object> agents() {
        List<String> names = patrol.knownAgents();
        return Map.of("agents", names, "count", names.size());
    }

    @GetMapping("/api/agents/{agent}/unread")
    public Map<String, Object> unread(@PathVariable String agent) {
        return Map.of("agent", agent, "unread", inbox.unreadCount(agent));
    }

    @GetMapping("/api/trace/{messageId}")
    public Map<String, Object> trace(@PathVariable String messageId) {
        return Map.of("message_id", messageId, "trace", archive.trace(messageId));
    }

    @GetMapping("/api/acceptance")
    public Map<String, Object> acceptance() {
        var items = acceptance.check();
        return Map.of("ok", acceptance.allOk(), "items", items);
    }

    @GetMapping("/api/events")
    public List<MessageEventLog.Event> recentEvents(@RequestParam(defaultValue = "50") int limit) {
        return events.latest(Math.min(Math.max(limit, 1), 500));
    }

    @PostMapping("/api/inbox/{agent}/archive")
    public Map<String, Object> archiveSettled(@PathVariable String agent) {
        ArchiveService.Outcome out = archive.archiveSettled(agent);
        return Map.of("agent", agent, "archived", out.archived(), "ids", out.ids());
    }
}
