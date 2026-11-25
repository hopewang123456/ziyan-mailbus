package io.github.hopewang123456.mailbus.workflow;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/workflows")
@Validated
public class WorkflowController {

    private final WorkflowService service;

    public WorkflowController(WorkflowService service) {
        this.service = service;
    }

    @GetMapping
    public WorkflowDtos.WorkflowListOut list(
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        return service.list(limit, offset);
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

    /** 旧别名：仅重命名，不进契约。 */
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
    public WorkflowDtos.VersionListOut versions(
            @PathVariable("workflow_id") String workflowId,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        return service.versions(workflowId, limit, offset);
    }

    @GetMapping("/{workflow_id}/versions/{version}/graph")
    public WorkflowDtos.GraphOut graph(
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version) {
        return service.graph(workflowId, version);
    }

    @PutMapping("/{workflow_id}/versions/{version}/graph")
    public WorkflowDtos.GraphOut saveGraph(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version,
            @RequestParam(defaultValue = "false") boolean force,
            @Valid @RequestBody WorkflowDtos.GraphIn input) {
        return service.saveGraph(actor, workflowId, version, input, force);
    }

    @PostMapping("/{workflow_id}/versions/{version}/validate")
    public WorkflowDtos.ValidateOut validate(
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version,
            @Valid @RequestBody(required = false) WorkflowDtos.GraphIn input) {
        return service.validate(workflowId, version, input);
    }

    @PostMapping("/{workflow_id}/versions/{version}/clone")
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowDtos.ContractVersionOut cloneVersion(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version) {
        return service.cloneVersion(actor, workflowId, version);
    }

    @PostMapping("/{workflow_id}/versions/{version}/publish")
    public WorkflowDtos.ContractVersionOut publish(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @PathVariable int version) {
        return service.publish(actor, workflowId, version);
    }

    /** 旧别名：新增草稿版本（节点仅名称），不进契约。 */
    @PostMapping("/{workflow_id}/versions")
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowDtos.VersionOut addVersion(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("workflow_id") String workflowId,
            @Valid @RequestBody WorkflowDtos.VersionIn input) {
        return service.addVersion(actor, workflowId, input);
    }
}
