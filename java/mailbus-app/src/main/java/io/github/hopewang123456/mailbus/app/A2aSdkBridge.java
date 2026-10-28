package io.github.hopewang123456.mailbus.app;

import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.TaskOperation;
import org.a2aproject.sdk.server.requesthandlers.RequestHandler;
import org.a2aproject.sdk.spec.A2AError;
import org.a2aproject.sdk.spec.CancelTaskParams;
import org.a2aproject.sdk.spec.DeleteTaskPushNotificationConfigParams;
import org.a2aproject.sdk.spec.EventKind;
import org.a2aproject.sdk.spec.GetTaskPushNotificationConfigParams;
import org.a2aproject.sdk.spec.ListTaskPushNotificationConfigsParams;
import org.a2aproject.sdk.spec.ListTaskPushNotificationConfigsResult;
import org.a2aproject.sdk.spec.ListTasksParams;
import org.a2aproject.sdk.spec.MessageSendParams;
import org.a2aproject.sdk.spec.StreamingEventKind;
import org.a2aproject.sdk.spec.Task;
import org.a2aproject.sdk.spec.TaskIdParams;
import org.a2aproject.sdk.spec.TaskPushNotificationConfig;
import org.a2aproject.sdk.spec.TaskQueryParams;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.TaskStatus;
import org.a2aproject.sdk.spec.TaskStatusUpdateEvent;

import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.lang.reflect.Type;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

/**
 * A2A 官方 SDK RequestHandler 桥（M2d-b1）— 把 SDK 0.3 协议面
 * （message/send · message/stream · tasks/get · tasks/cancel · tasks/list）
 * 桥到既有 TaskService 创建/取消链路，与 python {@code handlers_a2a} 的
 * 0.2 面（SendMessage 等）并行，wire 形状经 {@link A2aMessageMapper} 同源。
 */
public final class A2aSdkBridge implements RequestHandler {

    private static final Type MAP_TYPE = new com.google.gson.reflect.TypeToken<Map<String, Object>>() {
    }.getType();

    /** 流式轮询线程（daemon，全桥共享）。 */
    private static final ScheduledExecutorService POLLER = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "a2a-sdk-stream");
        t.setDaemon(true);
        return t;
    });

    static final long POLL_MS = 500;
    static final long STREAM_TIMEOUT_MS = 120_000;

    private final String agentId;
    private final TaskService tasks;
    private final TaskRepository repo;
    private final HumanQueueService humanQueue;

    public A2aSdkBridge(String agentId, TaskService tasks, TaskRepository repo, HumanQueueService humanQueue) {
        this.agentId = agentId;
        this.tasks = tasks;
        this.repo = repo;
        this.humanQueue = humanQueue;
    }

    // ---- message/send ----

    @Override
    public EventKind onMessageSend(MessageSendParams params, ServerCallContext ctx) throws A2AError {
        Map<String, Object> wire = createWireTask(params);
        return wireToSdkTask(wire);
    }

    // ---- tasks/get ----

    @Override
    public Task onGetTask(TaskQueryParams params, ServerCallContext ctx) throws A2AError {
        String tid = params == null || params.id() == null ? "" : params.id();
        return wireToSdkTask(hubTaskOrThrow(tid));
    }

    // ---- tasks/cancel ----

    @Override
    public Task onCancelTask(CancelTaskParams params, ServerCallContext ctx) throws A2AError {
        String tid = params == null || params.id() == null ? "" : params.id();
        Map<String, Object> hub = hubTaskOrThrow(tid);
        String mailbusTaskId = mailbusTaskIdOf(hub);
        tasks.fsmAction(mailbusTaskId, "cancel", Map.of("reason", "a2a_cancel"));
        Map<String, Object> wire = A2aMessageMapper.hubTask(findTask(mailbusTaskId), tid, humanQueue.items());
        return wireToSdkTask(wire);
    }

    // ---- tasks/list ----

    @Override
    public org.a2aproject.sdk.jsonrpc.common.wrappers.ListTasksResult onListTasks(ListTasksParams params,
                                                                                   ServerCallContext ctx)
            throws A2AError {
        List<Task> out = new ArrayList<>();
        for (Map<String, Object> doc : repo.listAll()) {
            String taskId = str(doc.get("task_id"));
            out.add(wireToSdkTask(A2aMessageMapper.hubTask(doc, taskId, humanQueue.items())));
        }
        return new org.a2aproject.sdk.jsonrpc.common.wrappers.ListTasksResult(out);
    }

    // ---- message/stream（SSE，python _stream_a2a_task_progress 对等） ----

    @Override
    public Flow.Publisher<StreamingEventKind> onMessageSendStream(MessageSendParams params, ServerCallContext ctx)
            throws A2AError {
        Map<String, Object> wire = createWireTask(params);
        String a2aTaskId = str(wire.get("id"));
        String mailbusTaskId = mailbusTaskIdOf(wire);

        // 同步派发：轮询线程内直接 onNext（SseEmitter.send 线程安全）。
        // 首帧=创建结果（working，python _send_sse_jsonrpc 对等）：SubmissionPublisher
        // 无订阅者时 submit 会被丢弃，故首帧等订阅者到达后补发；之后状态变化才推帧，
        // 终态（completed/failed/canceled/rejected）关流。
        SubmissionPublisher<StreamingEventKind> pub = new SubmissionPublisher<>(Runnable::run, 64);
        final String[] lastState = {str(wire.get("status"))};
        final boolean[] firstSent = {false};
        final long deadline = System.currentTimeMillis() + STREAM_TIMEOUT_MS;
        POLLER.scheduleAtFixedRate(() -> {
            try {
                if (!firstSent[0]) {
                    if (pub.getNumberOfSubscribers() == 0) {
                        return; // 等首个订阅者（首帧不能在订阅前 submit，会被丢弃）
                    }
                    pub.submit(statusEvent(wire));
                    firstSent[0] = true;
                }
                Map<String, Object> doc = findTask(mailbusTaskId);
                Map<String, Object> now = A2aMessageMapper.hubTask(doc, a2aTaskId, humanQueue.items());
                String state = str(now.get("status"));
                boolean terminal = state.equals("completed") || state.equals("failed")
                        || state.equals("canceled") || state.equals("rejected");
                if (!state.equals(lastState[0])) {
                    lastState[0] = state;
                    pub.submit(statusEvent(now));
                }
                if (terminal || System.currentTimeMillis() > deadline) {
                    if (!terminal) {
                        Map<String, Object> timeoutWire = new LinkedHashMap<>(now);
                        timeoutWire.put("status", "failed");
                        pub.submit(statusEvent(timeoutWire));
                    }
                    pub.close();
                    throw new IllegalStateException("stream-done");
                }
            } catch (IllegalStateException done) {
                throw done;
            } catch (RuntimeException e) {
                pub.closeExceptionally(e);
                throw new IllegalStateException("stream-done", e);
            }
        }, 0, POLL_MS, TimeUnit.MILLISECONDS);
        return pub;
    }

    // ---- 不支持的面（push-notification / subscribe） ----

    @Override
    public Flow.Publisher<StreamingEventKind> onSubscribeToTask(TaskIdParams params, ServerCallContext ctx)
            throws A2AError {
        throw unsupported("tasks/subscribe");
    }

    @Override
    public TaskPushNotificationConfig onCreateTaskPushNotificationConfig(TaskPushNotificationConfig config,
                                                                         ServerCallContext ctx) throws A2AError {
        throw unsupported("push-notification-config/set");
    }

    @Override
    public TaskPushNotificationConfig onGetTaskPushNotificationConfig(GetTaskPushNotificationConfigParams params,
                                                                      ServerCallContext ctx) throws A2AError {
        throw unsupported("push-notification-config/get");
    }

    @Override
    public ListTaskPushNotificationConfigsResult onListTaskPushNotificationConfigs(
            ListTaskPushNotificationConfigsParams params, ServerCallContext ctx) throws A2AError {
        throw unsupported("push-notification-config/list");
    }

    @Override
    public void onDeleteTaskPushNotificationConfig(DeleteTaskPushNotificationConfigParams params,
                                                   ServerCallContext ctx) throws A2AError {
        throw unsupported("push-notification-config/delete");
    }

    @Override
    public void authorizeTaskAccess(String taskId, ServerCallContext ctx, TaskOperation operation) {
        // mailbus A2A 面无 per-task 授权（与 0.2 面一致）
    }

    // ---- 内部 ----

    private Map<String, Object> createWireTask(MessageSendParams params) throws A2AError {
        Map<String, Object> message = recordToMap(params == null ? null : params.message());
        Map<String, Object> envelope = A2aMessageMapper.fromA2aTaskCreate(Map.of("message", message));
        envelope.put("target_agent", agentId);
        TaskService.Result r = tasks.createFromEnvelope(envelope);
        if (r.status() != 201) {
            throw new A2AError(-32602, "create failed: " + str(r.body().get("message"))
                    + str(r.body().get("error")), null);
        }
        Map<String, Object> task = toMap(r.body().get("task"));
        List<Map<String, Object>> chain = TaskFsmViews.chain(task);
        String stepId = chain.isEmpty() ? null : str(chain.get(0).get("step_id"));
        return A2aMessageMapper.wireTask(str(task.get("task_id")), stepId);
    }

    private Map<String, Object> hubTaskOrThrow(String a2aTaskId) throws A2AError {
        Map<String, Object> doc = findTaskByA2aId(a2aTaskId);
        if (doc == null) {
            throw new A2AError(-32001, "task_not_found", null);
        }
        return A2aMessageMapper.hubTask(doc, a2aTaskId, humanQueue.items());
    }

    private Map<String, Object> findTask(String mailbusTaskId) {
        for (Map<String, Object> doc : repo.listAll()) {
            if (mailbusTaskId.equals(str(doc.get("task_id")))) {
                return doc;
            }
        }
        return Map.of();
    }

    private Map<String, Object> findTaskByA2aId(String a2aTaskId) {
        for (Map<String, Object> doc : repo.listAll()) {
            if (a2aTaskId.equals(str(doc.get("task_id")))) {
                return doc;
            }
            boolean inChain = TaskFsmViews.chain(doc).stream()
                    .anyMatch(s -> a2aTaskId.equals(str(s.get("a2a_task_id"))));
            if (inChain) {
                return doc;
            }
        }
        return null;
    }

    /** wire task Map → SDK Task record（状态字符串→TaskState）。 */
    static Task wireToSdkTask(Map<String, Object> wire) {
        Map<String, Object> metadata = wire.get("metadata") instanceof Map<?, ?> m ? toMap(m) : Map.of();
        return Task.builder()
                .id(str(wire.get("id")))
                .contextId(mailbusTaskIdOf(wire))
                .status(new TaskStatus(wireState(str(wire.get("status")))))
                .metadata(metadata)
                .build();
    }

    static TaskStatusUpdateEvent statusEvent(Map<String, Object> wire) {
        Map<String, Object> metadata = wire.get("metadata") instanceof Map<?, ?> m ? toMap(m) : Map.of();
        return TaskStatusUpdateEvent.builder()
                .taskId(str(wire.get("id")))
                .contextId(mailbusTaskIdOf(wire))
                .status(new TaskStatus(wireState(str(wire.get("status")))))
                .metadata(metadata)
                .build();
    }

    static TaskState wireState(String wireStatus) {
        return switch (wireStatus == null ? "" : wireStatus) {
            case "submitted" -> TaskState.TASK_STATE_SUBMITTED;
            case "working" -> TaskState.TASK_STATE_WORKING;
            case "input-required" -> TaskState.TASK_STATE_INPUT_REQUIRED;
            case "completed" -> TaskState.TASK_STATE_COMPLETED;
            case "failed" -> TaskState.TASK_STATE_FAILED;
            case "canceled" -> TaskState.TASK_STATE_CANCELED;
            case "rejected" -> TaskState.TASK_STATE_REJECTED;
            default -> TaskState.TASK_STATE_UNSPECIFIED;
        };
    }

    private static String mailbusTaskIdOf(Map<String, Object> wire) {
        if (wire.get("metadata") instanceof Map<?, ?> meta && meta.get("mailbus") instanceof Map<?, ?> mb) {
            return str(mb.get("taskId"));
        }
        return str(wire.get("id"));
    }

    private static A2AError unsupported(String what) {
        return new A2AError(-32601, "method not supported by mailbus bridge: " + what, null);
    }

    /** SDK record → Map（Gson 往返；null 入参返回空 Map）。 */
    static Map<String, Object> recordToMap(Object record) {
        if (record == null) {
            return new LinkedHashMap<>();
        }
        try {
            return JsonUtil.OBJECT_MAPPER.fromJson(JsonUtil.toJson(record), MAP_TYPE);
        } catch (Exception e) {
            return new LinkedHashMap<>();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    /** 桥用流超时（供测试覆盖）。 */
    static Duration streamTimeout() {
        return Duration.ofMillis(STREAM_TIMEOUT_MS);
    }
}
