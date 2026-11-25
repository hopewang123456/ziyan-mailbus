package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.auth.Authz;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
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

import java.util.Map;

@RestController
@RequestMapping("/api/agents")
public class AgentController {

    private final AgentService service;
    private final AgentRegistrationService registration;

    public AgentController(AgentService service, AgentRegistrationService registration) {
        this.service = service;
        this.registration = registration;
    }

    @GetMapping
    public AgentDtos.AgentListOut list(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(defaultValue = "100") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        Authz.require(actor, Authz.ORG_MANAGE);
        return service.listPage(Math.min(Math.max(limit, 1), 500), Math.max(offset, 0));
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public AgentDtos.AgentRegisterOut register(
            @Valid @RequestBody AgentDtos.AgentRegisterIn input) {
        return registration.register(input);
    }

    @GetMapping("/{agent_id}")
    public AgentDtos.AgentOut detail(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        Authz.require(actor, Authz.ORG_MANAGE);
        return service.detail(agentId);
    }

    @DeleteMapping("/{agent_id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
                       @PathVariable("agent_id") String agentId) {
        service.delete(actor, agentId);
    }

    @PostMapping("/{agent_id}/rotate-token")
    public AgentDtos.AgentTokenOut rotate(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        return service.rotateToken(actor, agentId);
    }

    @PostMapping("/{agent_id}/revoke-token")
    public AgentDtos.AgentOut revoke(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        return service.revokeToken(actor, agentId);
    }

    @PostMapping("/{agent_id}/health")
    public AgentDtos.AgentHealthOut health(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        Authz.require(actor, Authz.CONSOLE_ADMIN);
        return service.health(agentId);
    }

    @PostMapping("/{agent_id}/endpoint/approve")
    public AgentDtos.AgentOut approve(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        return service.approveEndpoint(actor, agentId);
    }

    @PostMapping("/{agent_id}/endpoint/reject")
    public AgentDtos.AgentOut reject(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        return service.rejectEndpoint(actor, agentId);
    }

    @PostMapping("/{agent_id}/unbind")
    public AgentDtos.AgentOut unbind(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId) {
        return service.unbind(actor, agentId);
    }

    // ---- 旧别名（B8 删除） ----

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AgentDtos.AgentOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody AgentDtos.AgentIn input) {
        return service.create(actor, input);
    }

    @PatchMapping("/{agent_id}")
    public AgentDtos.AgentOut patch(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("agent_id") String agentId,
            @RequestBody Map<String, Object> fields) {
        return service.update(actor, agentId, fields);
    }
}
