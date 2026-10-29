package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.SharedRoots;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.AgentDirectory;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 邮箱面（批 A8，2026-10-29）— python handlers_inbox 对等：
 * GET/POST /api/send-msg · POST /api/mark-read/{agent} ·
 * POST /api/actions/update/{agent}/{msg_id} · GET /api/replies。
 * 消息走 java MessageRepository（一消息一文件），与 python inbox.json 不同源（已知差异）。
 */
@RestController
public class MailboxController {

    private final InboxService inbox;
    private final AgentDirectory agents;
    private final MessageRepository messages;

    public MailboxController(InboxService inbox,
                             @Qualifier("agentDirectory") AgentDirectory agents,
                             @Qualifier("messageRepository") MessageRepository messages) {
        this.inbox = inbox;
        this.agents = agents;
        this.messages = messages;
    }

    /** POST /api/send-msg — 手动发送（from 默认 api；agent 未注册 404）。 */
    @PostMapping("/api/send-msg")
    public ResponseEntity<Map<String, Object>> sendPost(@RequestBody Map<String, Object> body) {
        return send(body);
    }

    /** GET /api/send-msg — query 参数同形。 */
    @GetMapping("/api/send-msg")
    public ResponseEntity<Map<String, Object>> sendGet(@RequestParam(required = false) String to,
                                                       @RequestParam(required = false) String content,
                                                       @RequestParam(required = false) String from) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("to", to);
        body.put("content", content);
        body.put("from", from);
        return send(body);
    }

    private ResponseEntity<Map<String, Object>> send(Map<String, Object> body) {
        String to = str(body.get("to"));
        String content = str(body.get("content"));
        if (to.isEmpty() || content.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "fatal", "detail", "缺少 to 或 content"));
        }
        if (agents.findById(to).isEmpty()) {
            return ResponseEntity.status(404).body(Map.of(
                    "error", "not_found", "detail", "agent '" + to + "' 未注册"));
        }
        String from = body.get("from") == null || str(body.get("from")).isEmpty() ? "api" : str(body.get("from"));
        var record = inbox.send(to, from, content);
        return ResponseEntity.ok(Map.of("status", "ok", "msg_id", record.id()));
    }

    /** POST /api/mark-read/{agent} — 逐消息标记已读（java acknowledge 语义）。 */
    @PostMapping("/api/mark-read/{agent}")
    public ResponseEntity<Map<String, Object>> markRead(@PathVariable("agent") String agent,
                                                        @RequestBody Map<String, Object> body) {
        List<?> msgIds = body.get("msg_ids") instanceof List<?> l ? l : List.of();
        if (msgIds.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "fatal", "detail", "缺少 msg_ids"));
        }
        List<Map<String, Object>> results = new ArrayList<>();
        int marked = 0;
        for (Object id : msgIds) {
            var acked = inbox.acknowledge(String.valueOf(id));
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("msg_id", id);
            row.put("ok", acked.isPresent());
            results.add(row);
            if (acked.isPresent()) {
                marked++;
            }
        }
        return ResponseEntity.ok(Map.of("status", "ok", "marked", marked, "results", results));
    }

    /** POST /api/actions/update/{agent}/{msg_id} — 更新消息 action 字段。 */
    @PostMapping("/api/actions/update/{agent}/{msg_id}")
    public ResponseEntity<Map<String, Object>> actionsUpdate(@PathVariable("agent") String agent,
                                                             @PathVariable("msg_id") String msgId,
                                                             @RequestBody Map<String, Object> body) {
        Map<String, Object> action = body.get("action") instanceof Map<?, ?> a ? cast(a) : Map.of();
        if (action.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "fatal", "detail", "缺少 action"));
        }
        var found = messages.findById(msgId);
        if (found.isEmpty() || !agent.equals(found.get().toAgent())) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found", "detail", "inbox not found"));
        }
        // MsgRecord 无 action 字段——java 第一版返回合并视图不落盘（消息模型差异登记）
        Map<String, Object> merged = new LinkedHashMap<>(action);
        return ResponseEntity.ok(Map.of("status", "ok", "msg_id", msgId, "action", merged,
                "note", "java MsgRecord 无 action 字段，合并视图不落盘（批 A8 登记）"));
    }

    /** GET /api/replies — 各 agent 回复（type in reply/forward/task_reply）。 */
    @GetMapping("/api/replies")
    public Map<String, Object> replies() {
        Map<String, Object> results = new LinkedHashMap<>();
        for (var card : agents.findAll()) {
            String name = card.id();
            List<Map<String, Object>> replies = new ArrayList<>();
            for (var m : messages.findByAgentAndState(name, null)) {
                String type = m.type() == null ? "" : m.type();
                if (!type.equals("reply") && !type.equals("forward") && !type.equals("task_reply")) {
                    continue;
                }
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("id", m.id());
                row.put("from", m.fromAgent());
                row.put("type", m.type());
                row.put("content", m.content());
                String status = m.state() == null ? "" : m.state().name().toLowerCase();
                row.put("status", status);
                row.put("state", status);
                row.put("created_at", m.createdAt() == null ? "" : m.createdAt().toString());
                replies.add(row);
            }
            if (!replies.isEmpty()) {
                results.put(name, replies);
            }
        }
        return results;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
