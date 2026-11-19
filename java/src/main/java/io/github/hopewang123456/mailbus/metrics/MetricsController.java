package io.github.hopewang123456.mailbus.metrics;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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

    @GetMapping("/rules")
    public MetricDtos.MetricRuleListOut rules(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return new MetricDtos.MetricRuleListOut(service.listRules());
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
