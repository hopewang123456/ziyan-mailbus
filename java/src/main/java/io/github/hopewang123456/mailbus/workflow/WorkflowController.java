package io.github.hopewang123456.mailbus.workflow;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/workflows")
public class WorkflowController {

    private final WorkflowService service;

    public WorkflowController(WorkflowService service) {
        this.service = service;
    }

    @GetMapping
    public List<WorkflowDtos.WorkflowOut> list() {
        return service.list();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowDtos.WorkflowOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody WorkflowDtos.WorkflowIn input) {
        return service.create(actor, input);
    }

    @GetMapping("/{workflow_id}")
    public WorkflowDtos.WorkflowOut get(@PathVariable("workflow_id") String workflowId) {
        return service.get(workflowId);
    }

    @PatchMapping("/{workflow_id}")
    public WorkflowDtos.WorkflowOut rename(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @Valid @RequestBody WorkflowDtos.WorkflowIn input) {
        return service.rename(actor, workflowId, input);
    }

    @DeleteMapping("/{workflow_id}")
    public ResponseEntity<Void> delete(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId) {
        service.delete(actor, workflowId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{workflow_id}/versions")
    public List<WorkflowDtos.VersionOut> versions(
            @PathVariable("workflow_id") String workflowId) {
        return service.versions(workflowId);
    }

    @PostMapping("/{workflow_id}/versions")
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowDtos.VersionOut addVersion(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @Valid @RequestBody WorkflowDtos.VersionIn input) {
        return service.addVersion(actor, workflowId, input);
    }

    @GetMapping("/{workflow_id}/versions/{version}")
    public WorkflowDtos.VersionOut version(
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version) {
        return service.version(workflowId, version);
    }

    @PostMapping("/{workflow_id}/versions/{version}/publish")
    public WorkflowDtos.VersionOut publish(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version) {
        return service.publish(actor, workflowId, version);
    }
}
