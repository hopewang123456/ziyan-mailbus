package io.github.hopewang123456.mailbus.messaging;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api")
public class ChannelController {

    private final MessagingService service;

    public ChannelController(MessagingService service) {
        this.service = service;
    }

    @PostMapping("/mcp/messages")
    @ResponseStatus(HttpStatus.CREATED)
    public MessageDtos.MessageOut mcp(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody MessageDtos.MessageIn input) {
        return service.send(actor, input, "mcp");
    }

    @GetMapping("/mcp/pull")
    public List<MessageDtos.PullItem> pull(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.pull(actor);
    }
}
