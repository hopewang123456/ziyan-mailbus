package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.AcceptanceService;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.InboxService;
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
 * <p>501 惯例（D13 双栈对等）：依赖 java 独有存储、无 python 对等实现的
 * 端点显式 501 + 记录，不返回空壳假装可用。
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

    @GetMapping("/api/agents/{agent}/unread")
    public Map<String, Object> unread(@PathVariable String agent) {
        return Map.of("agent", agent, "unread", inbox.unreadCount(agent));
    }

    /**
     * 501（2026-10-27 PY4-A 拍板）：消息事件流依赖 java 独有的 SQLite
     * {@code msg_events} 表，python 侧无同源事件日志（消息文件布局也不同）。
     * 双栈同池前提（消息存储 SoT 统一）达成前，此端点显式声明不对等。
     */
    @GetMapping("/api/trace/{messageId}")
    public ResponseEntity<Map<String, Object>> trace(@PathVariable String messageId) {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED).body(Map.of(
                "status", "error",
                "error", "not_implemented",
                "message", "message event stream is java-only (SQLite msg_events); "
                        + "no python counterpart until message storage SoT is unified",
                "message_id", messageId));
    }

    @GetMapping("/api/acceptance")
    public Map<String, Object> acceptance() {
        var items = acceptance.check();
        return Map.of("ok", acceptance.allOk(), "items", items);
    }

    /**
     * 501（2026-10-27 PY4-A 拍板）：同 {@code /api/trace/{id}}——全局事件流
     * 依赖 java 独有的 SQLite {@code msg_events} 表。
     */
    @GetMapping("/api/events")
    public ResponseEntity<Map<String, Object>> recentEvents(@RequestParam(defaultValue = "50") int limit) {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED).body(Map.of(
                "status", "error",
                "error", "not_implemented",
                "message", "message event stream is java-only (SQLite msg_events); "
                        + "no python counterpart until message storage SoT is unified",
                "limit", Math.min(Math.max(limit, 1), 500)));
    }

    @PostMapping("/api/inbox/{agent}/archive")
    public Map<String, Object> archiveSettled(@PathVariable String agent) {
        ArchiveService.Outcome out = archive.archiveSettled(agent);
        return Map.of("agent", agent, "archived", out.archived(), "ids", out.ids());
    }
}
