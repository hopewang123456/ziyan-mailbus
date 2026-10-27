package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.CommandDraftService;
import io.github.hopewang123456.mailbus.app.CommandInboxService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 发令窗口聚合端点（M2c，python handlers_tasks command 域对等）：
 * GET /api/command/inbox（子言四路聚合）· POST /api/command/draft（D4 草稿预演）。
 */
@RestController
public class CommandController {

    private final CommandInboxService inbox;
    private final CommandDraftService draft;

    public CommandController(CommandInboxService inbox, CommandDraftService draft) {
        this.inbox = inbox;
        this.draft = draft;
    }

    @GetMapping("/api/command/inbox")
    public Map<String, Object> commandInbox() {
        return inbox.inbox();
    }

    @PostMapping("/api/command/draft")
    public ResponseEntity<Map<String, Object>> commandDraft(@RequestBody Map<String, Object> body) {
        Map<String, Object> out = draft.draft(
                body == null ? null : String.valueOf(body.get("intent")),
                body == null ? null : String.valueOf(body.get("task_type")),
                body == null ? null : String.valueOf(body.get("tier")));
        int status = ((Number) out.get("status")).intValue();
        @SuppressWarnings("unchecked")
        Map<String, Object> respBody = (Map<String, Object>) out.get("body");
        return ResponseEntity.status(status).body(respBody);
    }
}
