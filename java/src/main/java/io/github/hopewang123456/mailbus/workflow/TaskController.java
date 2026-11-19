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
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public List<TaskDtos.TaskOut> list(@RequestParam(required = false) String state,
                                       @RequestParam(name = "owner_id", required = false)
                                       String ownerId) {
        return service.list(state, ownerId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public TaskDtos.TaskOut create(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody TaskDtos.TaskIn input) {
        return service.create(actor, input);
    }

    @GetMapping("/{task_id}")
    public TaskDtos.TaskOut get(@PathVariable("task_id") String taskId) {
        return service.get(taskId);
    }

    @PostMapping("/{task_id}/dispatch")
    public TaskDtos.TaskOut dispatch(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId) {
        return service.dispatch(actor, taskId);
    }

    @PostMapping("/{task_id}/advance")
    public TaskDtos.TaskOut advance(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId,
            @Valid @RequestBody TaskDtos.TaskAdvanceIn input) {
        return service.advance(actor, taskId, input);
    }

    @PostMapping("/{task_id}/cancel")
    public TaskDtos.TaskOut cancel(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("task_id") String taskId) {
        return service.cancel(actor, taskId);
    }
}
