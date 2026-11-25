package io.github.hopewang123456.mailbus.workflow;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.common.ApiException;
import jakarta.validation.Valid;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

@RestController
@RequestMapping("/api")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping("/tasks")
    public TaskDtos.TaskListOut list(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) String state,
            @RequestParam(name = "owner_id", required = false) String ownerId,
            @RequestParam(name = "workflow_id", required = false) String workflowId,
            @RequestParam(defaultValue = "100") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        return service.list(actor, state, ownerId, workflowId,
                Math.max(1, Math.min(limit, 500)), Math.max(0, offset));
    }

    @PostMapping("/tasks")
    @ResponseStatus(HttpStatus.CREATED)
    public TaskDtos.TaskDetailOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody TaskDtos.TaskCreateIn input) {
        return service.create(actor, input);
    }

    @GetMapping("/tasks/summary")
    public TaskDtos.TaskCountersOut summary(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return service.counters(actor);
    }

    @GetMapping("/tasks/{task_id}")
    public TaskDtos.TaskDetailOut get(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId) {
        return service.get(actor, taskId);
    }

    @GetMapping("/tasks/{task_id}/trace")
    public TaskDtos.TaskTraceOut trace(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId) {
        return service.trace(actor, taskId);
    }

    @PostMapping("/tasks/{task_id}/nodes/{node_id}/claim")
    public TaskDtos.TaskDetailOut claim(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @PathVariable("node_id") String nodeId) {
        return service.claim(actor, taskId, nodeId);
    }

    @PostMapping("/tasks/{task_id}/nodes/{node_id}/result")
    public TaskDtos.TaskDetailOut submit(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @PathVariable("node_id") String nodeId,
            @Valid @RequestBody TaskDtos.ResultIn input) {
        return service.submit(actor, taskId, nodeId, input);
    }

    @PostMapping("/tasks/{task_id}/cancel")
    public TaskDtos.TaskDetailOut cancel(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @Valid @RequestBody(required = false) TaskDtos.CancelIn input) {
        return service.cancel(actor, taskId, input == null ? null : input.reason());
    }

    @PostMapping("/tasks/{task_id}/nodes/{node_id}/rerun-join")
    public TaskDtos.TaskDetailOut rerunJoin(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @PathVariable("node_id") String nodeId,
            @Valid @RequestBody TaskDtos.RerunJoinIn input) {
        return service.rerunJoin(actor, taskId, nodeId, input);
    }

    @PostMapping("/tasks/{task_id}/nodes/{node_id}/artifacts")
    public TaskDtos.ArtifactOut upload(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @PathVariable("node_id") String nodeId,
            @RequestParam("file") MultipartFile file,
            @RequestParam(name = "description", required = false) String description)
            throws IOException {
        if (file.getSize() > 100L * 1024 * 1024) {
            throw ApiException.unprocessable("unprocessable", "产物文件超过 100MB 上限");
        }
        return service.upload(actor, taskId, nodeId,
                file.getOriginalFilename(), file.getBytes(), description);
    }

    @GetMapping("/artifacts/{artifact_id}/download")
    public ResponseEntity<Resource> download(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("artifact_id") String artifactId) {
        TaskService.DownloadFile file = service.download(actor, artifactId);
        String encoded = URLEncoder.encode(file.fileName(), StandardCharsets.UTF_8)
                .replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + encoded)
                .body(new FileSystemResource(file.path()));
    }
}
