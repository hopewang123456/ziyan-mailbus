package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.A2aRpcService;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.Map;

/**
 * A2A 端点（M2d-a，python handlers_a2a 对等）：
 * GET /api/a2a/agent-cards · /api/a2a/agent-card/{id} · /api/a2a/protocol ·
 * POST /api/a2a/rpc/{agent}（JSON-RPC SendMessage/GetTask/CancelTask）。
 */
@RestController
public class A2aController {

    private final A2aRpcService rpc;
    private final Path dataDir;

    public A2aController(A2aRpcService rpc, Environment env) {
        this.rpc = rpc;
        this.dataDir = io.github.hopewang123456.mailbus.app.SharedRoots
                .resolveDataDir(env.getProperty("mailbus.data-dir"));
    }

    @GetMapping("/api/a2a/agent-cards")
    public Map<String, Object> cards() {
        return rpc.agentCards();
    }

    @GetMapping("/api/a2a/agent-card/{id}")
    public ResponseEntity<Map<String, Object>> card(@PathVariable("id") String id) {
        Map<String, Object> cards = rpc.agentCards();
        Object found = ((java.util.List<?>) cards.get("items")).stream()
                .filter(i -> id.equals(String.valueOf(((Map<?, ?>) i).get("agent_id"))))
                .findFirst().orElse(null);
        if (found == null) {
            return ResponseEntity.status(404).body(Map.of("error", "not_found"));
        }
        return ResponseEntity.ok(Map.of("status", "ok", "agent_id", id, "wire", found));
    }

    @GetMapping("/api/a2a/protocol")
    public Map<String, Object> protocol() {
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("config/a2a-protocol.json"));
        return Map.of("status", "ok", "protocol", doc == null ? Map.of() : doc);
    }

    @PostMapping("/api/a2a/rpc/{agent}")
    public ResponseEntity<Map<String, Object>> rpc(@PathVariable("agent") String agent,
                                                   @RequestBody Map<String, Object> body) {
        Map<String, Object> out = rpc.rpc(agent, body);
        int status = ((Number) out.get("status")).intValue();
        @SuppressWarnings("unchecked")
        Map<String, Object> respBody = (Map<String, Object>) out.get("body");
        return ResponseEntity.status(status).body(respBody);
    }
}
