package io.github.hopewang123456.mailbus.messaging;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api")
@Validated
public class MessageController {

    private final MessagingService service;

    public MessageController(MessagingService service) {
        this.service = service;
    }

    @GetMapping("/inbox")
    public List<MessageDtos.MessageOut> inbox(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.inbox(actor);
    }

    @GetMapping("/messages")
    public List<MessageDtos.MessageOut> list(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) String agent,
            @RequestParam(required = false)
            @Pattern(regexp = "pending|delivered|failed") String status,
            @RequestParam(required = false) String since,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit) {
        return service.list(actor, agent, status, since, limit);
    }

    @PostMapping("/messages")
    @ResponseStatus(HttpStatus.CREATED)
    public MessageDtos.MessageOut send(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody MessageDtos.MessageIn input) {
        return service.send(actor, input, input.channel() == null ? "file_bus" : input.channel());
    }

    @GetMapping("/messages/{message_id}")
    public MessageDtos.MessageOut get(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("message_id") String messageId) {
        return service.get(actor, messageId);
    }

    @GetMapping("/messages/{message_id}/attempts")
    public List<MessageDtos.DeliveryAttemptOut> attempts(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("message_id") String messageId) {
        return service.attempts(actor, messageId);
    }
}
