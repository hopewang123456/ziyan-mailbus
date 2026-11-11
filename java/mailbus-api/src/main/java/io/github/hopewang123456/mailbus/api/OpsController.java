package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.AcceptanceService;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.PatrolService;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
 *
 * <p>D16 批4：消息存储 SoT 统一后，{@code /api/trace}、{@code /api/events}
 * 已转正（不再是 501）。
 */
@RestController
public class OpsController {

    private final PatrolService patrol;
    private final ArchiveService archive;
    private final AcceptanceService acceptance;
    private final io.github.hopewang123456.mailbus.app.MessageQueryService query;
    private final io.github.hopewang123456.mailbus.app.MessageTraceService traceService;
    private final io.github.hopewang123456.mailbus.app.StatusService status;

    public OpsController(PatrolService patrol, ArchiveService archive,
                         AcceptanceService acceptance,
                         io.github.hopewang123456.mailbus.app.MessageQueryService query,
                         io.github.hopewang123456.mailbus.app.MessageTraceService traceService,
                         io.github.hopewang123456.mailbus.app.StatusService status) {
        this.patrol = patrol;
        this.archive = archive;
        this.acceptance = acceptance;
        this.query = query;
        this.traceService = traceService;
        this.status = status;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "ts", java.time.Instant.now().toString());
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

    /** D16 批2：未读数切到 python SoT 投影（非终态消息数，与 python 同口径）。 */
    @GetMapping("/api/agents/{agent}/unread")
    public Map<String, Object> unread(@PathVariable String agent) {
        return Map.of("agent", agent, "unread", query.unread(agent));
    }

    /**
     * D16 批4 转正：消息快照读统一 SoT（python inbox.json 投影），事件流读 java
     * append-only {@code msg_events}（D4 派生投影）。消息已归档但事件仍在时照常返回。
     */
    @GetMapping("/api/trace/{messageId}")
    public ResponseEntity<Map<String, Object>> trace(@PathVariable String messageId) {
        return traceService.trace(messageId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                        "status", "error",
                        "error", "not_found",
                        "message", "no message or events for this id",
                        "message_id", messageId)));
    }

    @GetMapping("/api/acceptance")
    public Map<String, Object> acceptance() {
        var items = acceptance.check();
        return Map.of("ok", acceptance.allOk(), "items", items);
    }

    /** D16 批4 转正：最近事件（java 侧派生事件流，供 UI/排障）。 */
    @GetMapping("/api/events")
    public Map<String, Object> recentEvents(@RequestParam(defaultValue = "50") int limit) {
        return traceService.recentEvents(limit);
    }

    @PostMapping("/api/inbox/{agent}/archive")
    public Map<String, Object> archiveSettled(@PathVariable String agent) {
        ArchiveService.Outcome out = archive.archiveSettled(agent);
        return Map.of("agent", agent, "archived", out.archived(), "ids", out.ids());
    }
}
