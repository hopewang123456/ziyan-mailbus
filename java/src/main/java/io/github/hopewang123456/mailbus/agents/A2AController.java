package io.github.hopewang123456.mailbus.agents;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/a2a")
public class A2AController {

    private final AgentA2AService service;

    public A2AController(AgentA2AService service) {
        this.service = service;
    }

    @PostMapping("/messages")
    @ResponseStatus(HttpStatus.CREATED)
    public AgentDtos.A2aAckOut push(
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestBody AgentDtos.A2aMessageIn message) {
        Agent agent = service.authenticate(bearer(authorization));
        return service.handle(agent, message);
    }

    private String bearer(String value) {
        if (value == null) {
            return null;
        }
        String[] parts = value.split(" ", 2);
        if (parts.length != 2 || !"bearer".equalsIgnoreCase(parts[0])
                || parts[1].isBlank()) {
            return null;
        }
        return parts[1].strip();
    }
}
