package io.github.hopewang123456.mailbus.collab;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.AuthFilter;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.layout.LayoutService;
import io.github.hopewang123456.mailbus.messaging.MessageDtos;
import io.github.hopewang123456.mailbus.workflow.TaskDtos;
import io.github.hopewang123456.mailbus.workflow.TaskService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
@Validated
public class CollabController {

    private final ScreenService screens;
    private final PairService pairs;
    private final CollabMessageService messages;
    private final CollabStreamService streamService;
    private final LayoutService layout;
    private final TaskService tasks;

    public CollabController(ScreenService screens, PairService pairs,
                            CollabMessageService messages,
                            CollabStreamService streamService,
                            LayoutService layout, TaskService tasks) {
        this.screens = screens;
        this.pairs = pairs;
        this.messages = messages;
        this.streamService = streamService;
        this.layout = layout;
        this.tasks = tasks;
    }

    @GetMapping("/collab/screens")
    public ScreenDtos.ScreenListOut listScreens(
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        return screens.listPage(limit, offset);
    }

    @PatchMapping("/collab/screens/{screen_id}")
    public ScreenDtos.ScreenConfigOut updateScreen(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("screen_id") String screenId,
            @Valid @RequestBody ScreenDtos.ScreenDraftIn input) {
        return screens.saveDraft(actor, screenId, input);
    }

    @PostMapping("/collab/screens/{screen_id}/publish")
    public ScreenDtos.ScreenPublishOut publishScreen(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("screen_id") String screenId,
            @Valid @RequestBody ScreenDtos.ScreenPublishIn input) {
        return screens.publish(actor, screenId, input.expectedConfigVersion());
    }

    @PostMapping("/collab/screens/{screen_id}/focus")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void focus(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("screen_id") String screenId,
            @Valid @RequestBody ScreenDtos.ScreenFocusIn input) {
        screens.focus(actor, screenId, input.floorId(), input.seatId());
    }

    @DeleteMapping("/collab/screens/{screen_id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteScreen(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("screen_id") String screenId) {
        screens.delete(actor, screenId);
    }

    @GetMapping(value = "/collab/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor) {
        return streamService.subscribe(null);
    }

    @PostMapping("/public/collab/screens")
    @ResponseStatus(HttpStatus.CREATED)
    public ScreenDtos.ScreenRegisterOut publicRegister(
            @Valid @RequestBody ScreenDtos.ScreenRegisterIn input,
            HttpServletRequest request) {
        ScreenService.Registered registered = screens.register(request.getRemoteAddr(), input);
        return new ScreenDtos.ScreenRegisterOut(registered.screen().screenId(),
                registered.secret(), registered.screen().configVersion());
    }

    @PostMapping("/public/collab/screens/{screen_id}/heartbeat")
    public Map<String, Boolean> publicHeartbeat(
            @PathVariable("screen_id") String screenId,
            @RequestHeader(name = "X-Screen-Secret", required = false) String secret,
            HttpServletRequest request) {
        screens.heartbeat(request.getRemoteAddr(), screenId, secret);
        return Map.of("ok", true);
    }

    @PostMapping("/public/collab/screens/{screen_id}/leave")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void publicLeave(
            @PathVariable("screen_id") String screenId,
            @RequestHeader(name = "X-Screen-Secret", required = false) String secret,
            HttpServletRequest request) {
        screens.leave(request.getRemoteAddr(), screenId, secret);
    }

    @GetMapping("/public/collab/screens/{screen_id}/config")
    public ScreenDtos.PublicScreenConfigOut publicConfig(
            @PathVariable("screen_id") String screenId) {
        return screens.publicConfig(screenId);
    }

    @GetMapping(value = "/public/collab/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter publicStream(
            @RequestParam(name = "screen_id", required = false) String screenId) {
        String target = screenId == null || screenId.isBlank() ? null : screenId;
        if (target != null) {
            screens.publishedTeamId(target);
        }
        return streamService.subscribe(target, true);
    }

    @GetMapping("/collab/pairs")
    public List<CollabDtos.PairOut> listPairs(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(required = false) @Pattern(regexp = "active|ended") String state,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit) {
        return pairs.list(actor, state, limit);
    }

    @PostMapping("/collab/pairs")
    @ResponseStatus(HttpStatus.CREATED)
    public CollabDtos.PairOut createPair(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody CollabDtos.PairIn input) {
        return pairs.create(actor, input.partnerId());
    }

    @PostMapping("/collab/pairs/{pair_id}/end")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void endPair(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @PathVariable("pair_id") String pairId) {
        pairs.end(actor, pairId);
    }

    @GetMapping("/collab/messages")
    public List<MessageDtos.MessageOut> listCollabMessages(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @RequestParam(name = "pair_id", required = false) String pairId,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit) {
        return messages.list(actor, pairId, limit);
    }

    @PostMapping("/collab/messages")
    @ResponseStatus(HttpStatus.CREATED)
    public MessageDtos.MessageOut sendCollabMessage(
            @RequestAttribute(AuthFilter.ACTOR_ATTRIBUTE) Actor actor,
            @Valid @RequestBody CollabDtos.CollabMessageIn input) {
        return messages.send(actor, input);
    }

    @GetMapping("/public/collab/messages")
    public List<MessageDtos.MessageOut> publicCollabMessages(
            @RequestParam(name = "pair_id") String pairId,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int limit) {
        return messages.publicList(pairId, limit);
    }

    @GetMapping("/public/collab/seats/{seat_id}/tasks")
    public List<TaskDtos.PublicTaskOut> publicSeatTasks(
            @PathVariable("seat_id") String seatId) {
        LayoutService.SeatLookup seat = layout.lookupSeat(seatId);
        if (!seat.exists()) {
            throw ApiException.notFound("工位不存在");
        }
        if (seat.ownerId() == null) {
            return List.of();
        }
        return tasks.listByOwner(seat.ownerId()).stream()
                .map(TaskDtos.PublicTaskOut::of)
                .toList();
    }

    @GetMapping("/public/collab/tasks/{task_id}")
    public TaskDtos.PublicTaskOut publicTask(
            @PathVariable("task_id") String taskId,
            @RequestParam(name = "owner_id", required = false) String ownerId) {
        TaskDtos.TaskDetailOut task = tasks.getInternal(taskId);
        if (ownerId != null && !ownerId.equals(task.ownerId())) {
            throw ApiException.notFound("任务不存在");
        }
        return TaskDtos.PublicTaskOut.of(task);
    }
}
