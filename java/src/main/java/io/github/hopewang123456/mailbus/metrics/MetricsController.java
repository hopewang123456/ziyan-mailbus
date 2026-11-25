package io.github.hopewang123456.mailbus.metrics;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/metrics")
@Validated
public class MetricsController {

    private final MetricsService service;

    public MetricsController(MetricsService service) {
        this.service = service;
    }

    @GetMapping("/manifest")
    public MetricDtos.MetricManifestOut manifest(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return new MetricDtos.MetricManifestOut(service.manifest());
    }

    @GetMapping("/query")
    public MetricDtos.MetricQueryOut query(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) List<String> metric,
            @RequestParam(defaultValue = "1h") String granularity,
            @RequestParam(defaultValue = "24") @Min(1) @Max(720) int hours) {
        return service.query(metric, granularity, hours);
    }

    @GetMapping("/overview")
    public MetricDtos.MetricOverviewOut overview(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(value = "from", required = false) String from,
            @RequestParam(required = false) String to) {
        return service.overviewReport(actor, from, to);
    }

    @GetMapping("/trend")
    public MetricDtos.MetricTrendOut trend(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) List<String> metric,
            @RequestParam(value = "from", required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(defaultValue = "1h") String bucket) {
        return service.trendReport(actor, metric, from, to, bucket);
    }

    @GetMapping("/breakdown")
    public MetricDtos.MetricBreakdownOut breakdown(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) String metric,
            @RequestParam(value = "from", required = false) String from,
            @RequestParam(required = false) String to) {
        return service.breakdownReport(actor, metric, from, to);
    }

    @GetMapping("/export")
    public ResponseEntity<byte[]> export(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) List<String> metric,
            @RequestParam(value = "from", required = false) String from,
            @RequestParam(required = false) String to) {
        byte[] content = service.exportCsv(actor, from, to).getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
                .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"metrics.csv\"")
                .body(content);
    }

    @GetMapping("/rules")
    public MetricDtos.MetricRulePageOut rules(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        List<MetricDtos.MetricRuleOut> rules = service.listRules();
        int start = Math.min(offset, rules.size());
        int end = Math.min(start + limit, rules.size());
        return new MetricDtos.MetricRulePageOut(rules.subList(start, end),
                rules.size(), limit, offset);
    }

    @GetMapping("/rules/{rule_id}")
    public MetricDtos.MetricRuleOut getRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("rule_id") String ruleId) {
        return service.getRule(ruleId);
    }

    @PatchMapping("/rules/{rule_id}")
    public MetricDtos.MetricRuleOut updateRule(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("rule_id") String ruleId,
            @Valid @RequestBody MetricDtos.MetricRuleUpdateIn input) {
        return service.updateRule(actor, ruleId, input.fields());
    }

    @GetMapping("/layout")
    public MetricDtos.MetricLayoutViewOut layout(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.layout();
    }

    @PatchMapping("/layout")
    public MetricDtos.MetricLayoutViewOut updateLayout(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody MetricDtos.MetricLayoutIn input) {
        return service.updateLayout(actor, input.hidden());
    }
}
