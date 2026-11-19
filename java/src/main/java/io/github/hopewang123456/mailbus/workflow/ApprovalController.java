package io.github.hopewang123456.mailbus.workflow;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
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

import java.util.List;

@RestController
@RequestMapping("/api/approvals")
public class ApprovalController {

    private final ApprovalService service;

    public ApprovalController(ApprovalService service) {
        this.service = service;
    }

    @GetMapping
    public List<ApprovalDtos.ApprovalOut> list(
            @RequestParam(required = false) String status,
            @RequestParam(name = "task_id", required = false) String taskId) {
        return service.list(status, taskId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApprovalDtos.ApprovalOut request(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody ApprovalDtos.ApprovalIn input) {
        return service.request(actor, input);
    }

    @GetMapping("/{approval_id}")
    public ApprovalDtos.ApprovalOut get(@PathVariable("approval_id") String approvalId) {
        return service.get(approvalId);
    }

    @PostMapping("/{approval_id}/resolve")
    public ApprovalDtos.ApprovalOut resolve(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("approval_id") String approvalId,
            @Valid @RequestBody ApprovalDtos.ResolveIn input) {
        return service.resolve(actor, approvalId, input);
    }
}
