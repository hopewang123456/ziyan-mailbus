package io.github.hopewang123456.mailbus.audit;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.metrics.MetricDtos;
import io.github.hopewang123456.mailbus.ops.OpsModels;
import io.github.hopewang123456.mailbus.ops.OpsService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.util.Map;

@Validated
@RestController
@RequestMapping("/api")
public class AuditController {

    private final AuditService service;
    private final OpsService ops;

    public AuditController(AuditService service, OpsService ops) {
        this.service = service;
        this.ops = ops;
    }

    @GetMapping("/tasks/audit/stats")
    public MetricDtos.AuditStatsOut stats(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.stats();
    }

    @GetMapping("/audit")
    public ResponseEntity<?> audit(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor current,
            @RequestParam(required = false) String actor,
            @RequestParam(required = false) String action,
            @RequestParam(required = false) String resource,
            @RequestParam(name = "from", required = false) String from,
            @RequestParam(name = "to", required = false) String to,
            @RequestParam(required = false) String format,
            @Min(1) @Max(500) @RequestParam(defaultValue = "100") int limit,
            @Min(0) @RequestParam(defaultValue = "0") int offset) {
        Double start = OpsService.parseTime(from);
        Double end = OpsService.parseTime(to);
        if ("csv".equals(format)) {
            byte[] content = ops.exportAuditCsv(current, actor, action, resource, start, end)
                    .getBytes(StandardCharsets.UTF_8);
            return ResponseEntity.ok()
                    .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"audit.csv\"")
                    .body(content);
        }
        return ResponseEntity.ok(ops.listAudit(
                current, actor, action, resource, start, end, limit, offset));
    }

    @GetMapping("/audit/{audit_id}")
    public OpsModels.AuditEntry auditDetail(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("audit_id") long auditId) {
        return ops.getAudit(actor, auditId);
    }

    @GetMapping("/alerts")
    public OpsModels.Page<OpsModels.Alert> alerts(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) String state,
            @RequestParam(required = false) String severity,
            @Min(1) @Max(500) @RequestParam(defaultValue = "100") int limit,
            @Min(0) @RequestParam(defaultValue = "0") int offset) {
        return ops.listAlerts(actor, state, severity, limit, offset);
    }

    @PostMapping("/alerts/{alert_id}/ack")
    public OpsModels.Alert ackAlert(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("alert_id") String alertId) {
        return ops.ackAlert(actor, alertId);
    }

    @GetMapping("/alert-rules")
    public OpsModels.Page<OpsModels.AlertRule> listAlertRules(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Min(1) @Max(500) @RequestParam(defaultValue = "100") int limit,
            @Min(0) @RequestParam(defaultValue = "0") int offset) {
        return ops.listRules(actor, limit, offset);
    }

    @PostMapping("/alert-rules")
    @ResponseStatus(HttpStatus.CREATED)
    public OpsModels.AlertRule createAlertRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody OpsModels.AlertRuleIn input) {
        return ops.createRule(actor, input);
    }

    @PatchMapping("/alert-rules/{rule_id}")
    public OpsModels.AlertRule updateAlertRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("rule_id") String ruleId,
            @RequestBody Map<String, Object> changes) {
        return ops.updateRule(actor, ruleId, changes);
    }

    @DeleteMapping("/alert-rules/{rule_id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteAlertRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("rule_id") String ruleId) {
        ops.deleteRule(actor, ruleId);
    }

    @PostMapping("/alert-rules/{rule_id}/test")
    public OpsModels.AlertRuleTestOut testAlertRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("rule_id") String ruleId) {
        return ops.testRule(actor, ruleId);
    }
}
