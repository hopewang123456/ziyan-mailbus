package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.auth.Authz;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/agent-invites")
public class AgentInviteController {

    private final AgentRegistrationService service;

    public AgentInviteController(AgentRegistrationService service) {
        this.service = service;
    }

    @GetMapping
    public AgentDtos.AgentInviteListOut list(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(defaultValue = "100") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        Authz.require(actor, Authz.CONSOLE_ADMIN);
        return service.listInvites(Math.min(Math.max(limit, 1), 500), Math.max(offset, 0));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AgentDtos.AgentInviteOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody AgentDtos.AgentInviteIn input) {
        return service.createInvite(actor, input);
    }

    @PostMapping("/{invite_id}/revoke")
    public AgentDtos.AgentInviteOut revoke(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("invite_id") String inviteId) {
        return service.revokeInvite(actor, inviteId);
    }
}
