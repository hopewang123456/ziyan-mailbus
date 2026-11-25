package io.github.hopewang123456.mailbus.integrations;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class IntegrationController {

    private final IntegrationService service;

    public IntegrationController(IntegrationService service) {
        this.service = service;
    }

    @GetMapping("/settings/integrations")
    public IntegrationDtos.IntegrationsOut list(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.listIntegrations();
    }

    @PostMapping("/settings/integrations")
    public IntegrationDtos.PluginActionOut mutate(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody IntegrationDtos.PluginActionIn input) {
        return service.mutatePlugins(actor, input.action(), input.spec());
    }

    @PostMapping("/settings/integrations/{name}/invoke")
    public IntegrationDtos.IntegrationInvokeOut invoke(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable String name,
            @Valid @RequestBody IntegrationDtos.IntegrationInvokeIn input) {
        return service.invoke(actor, name, input.action(), input.params());
    }

    @GetMapping("/settings/env")
    public IntegrationDtos.EnvGroupsOut env(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.envGroups();
    }

    @PostMapping("/settings/env")
    public IntegrationDtos.EnvGroupsOut updateEnv(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody IntegrationDtos.EnvUpdateIn input) {
        return service.updateEnv(actor, input.vars());
    }

    @PostMapping("/dev/reload")
    public IntegrationDtos.ReloadOut reload(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.reload(actor);
    }
}
