package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/** Thin REST surface (grows toward the frozen OpenAPI contract in M2). */
@RestController
@RequestMapping("/api/inbox")
public class InboxController {

    private final InboxService inbox;

    public InboxController(InboxService inbox) {
        this.inbox = inbox;
    }

    @GetMapping("/{agent}")
    public List<MsgRecord> inbox(@PathVariable String agent) {
        return inbox.inbox(agent);
    }

    @PostMapping("/{agent}/send")
    public Map<String, Object> send(@PathVariable String agent, @RequestBody Map<String, String> body) {
        MsgRecord record = inbox.send(agent, body.getOrDefault("from", "system"), body.getOrDefault("content", ""));
        return Map.of("id", record.id(), "state", record.state().name());
    }

    @PostMapping("/ack/{messageId}")
    public Map<String, Object> ack(@PathVariable String messageId) {
        return inbox.acknowledge(messageId)
                .map(r -> Map.<String, Object>of("id", r.id(), "state", r.state().name()))
                .orElseGet(() -> Map.of("error", "not found: " + messageId));
    }
}
