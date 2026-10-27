package io.github.hopewang123456.mailbus.api;

import io.github.hopewang123456.mailbus.app.ResultIngestService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * POST /api/agents/{agent}/step-result — agent 工单执行回执（M2b，
 * python handlers_step_result 对等）。Thin REST surface；校验、落盘与
 * 立即推进（G-02）都在 {@link ResultIngestService}。
 */
@RestController
public class StepResultController {

    private final ResultIngestService ingest;

    public StepResultController(ResultIngestService ingest) {
        this.ingest = ingest;
    }

    @PostMapping("/api/agents/{agent}/step-result")
    public ResponseEntity<Map<String, Object>> submit(@PathVariable("agent") String agent,
                                                      @RequestBody Map<String, Object> body) {
        Map<String, Object> out = ingest.submitStepResult(agent, body);
        int status = ((Number) out.get("status")).intValue();
        @SuppressWarnings("unchecked")
        Map<String, Object> respBody = (Map<String, Object>) out.get("body");
        return ResponseEntity.status(status).body(respBody);
    }
}
