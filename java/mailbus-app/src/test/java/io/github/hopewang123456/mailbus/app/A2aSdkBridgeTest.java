package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.jsonrpc.common.wrappers.SendMessageRequest;
import org.a2aproject.sdk.spec.A2AError;
import org.a2aproject.sdk.spec.MessageSendParams;
import org.a2aproject.sdk.spec.StreamingEventKind;
import org.a2aproject.sdk.spec.Task;
import org.a2aproject.sdk.spec.TaskQueryParams;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.CancelTaskParams;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2d-b1 SDK 面 — RequestHandler 桥四方法 + 流式（0.3 协议语义，
 * wire 形状与 0.2 面 {@link A2aRpcShapeTest} 同源断言）。
 */
class A2aSdkBridgeTest {

    @TempDir
    Path dataDir;

    private A2aSdkBridge bridge;
    private FileTaskRepository repo;
    private TaskService tasks;

    @BeforeEach
    void setUp() throws IOException {
        Files.createDirectories(dataDir.resolve("roles/json"));
        Files.writeString(dataDir.resolve("roles/json/role-types.json"), """
                {"roles": {"1": {"key": "designer", "display": {"zh": "方案设计师"}, "candidates": ["agentA", "agentB"]},
                           "8": {"key": "developer", "display": {"zh": "开发工程师"}, "candidates": ["agentB"]}}}
                """);
        Files.writeString(dataDir.resolve("config.json"), """
                {"agents": {"agentA": {"concurrency": 1}, "agentB": {"concurrency": 1}}}
                """);
        Files.createDirectories(dataDir.resolve("inbox/agentA"));
        Files.createDirectories(dataDir.resolve("inbox/agentB"));
        repo = new FileTaskRepository(dataDir);
        Clock clock = Clock.systemUTC();
        HumanQueueService humanQueue = new HumanQueueService(dataDir, clock);
        tasks = new TaskService(dataDir, clock, repo,
                new RoleResolverService(dataDir, repo), humanQueue);
        tasks.setPlanner(new TaskPlannerService(dataDir, null));
        bridge = new A2aSdkBridge("agentA", tasks, repo, humanQueue);
    }

    /** 走 controller 同款反序列化路径：raw JSON → SDK wrapper（Part 适配器一并验证）。 */
    private static MessageSendParams sendParams(String taskId) throws Exception {
        String raw = "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"SendMessage\",\"params\":{"
                + "\"message\":{\"role\":\"ROLE_USER\",\"messageId\":\"msg-" + taskId + "\","
                + "\"parts\":[{\"text\":\"外部 A2A 需求：SDK 面\"}],"
                + "\"metadata\":{\"mailbus\":{\"taskId\":\"" + taskId + "\","
                + "\"planned_chain\":[{\"role_type\":1}]}}}}}";
        SendMessageRequest req = JsonUtil.fromJson(raw, SendMessageRequest.class);
        return req.getParams();
    }

    @Test
    void messageSendCreatesTaskViaM2aPipeline() throws Exception {
        Task task = (Task) bridge.onMessageSend(sendParams("ext-sdk-001"), null);
        assertEquals("ext-sdk-001", task.id());
        assertEquals(TaskState.TASK_STATE_WORKING, task.status().state());
        assertEquals("ext-sdk-001", task.contextId());
        assertEquals("ext-sdk-001",
                ((Map<?, ?>) task.metadata().get("mailbus")).get("taskId"));
        assertTrue(repo.find("ext-sdk-001").isPresent());
        assertEquals("created", ((Map<?, ?>) repo.find("ext-sdk-001").orElseThrow().get("fsm")).get("state"));
    }

    @Test
    void getTaskRichStatusAndMiss() throws Exception {
        bridge.onMessageSend(sendParams("ext-sdk-get"), null);
        Task task = bridge.onGetTask(new TaskQueryParams("ext-sdk-get"), null);
        // M 级默认待批 → input-required（hubTask 富状态，与 0.2 面同语义）
        assertEquals(TaskState.TASK_STATE_INPUT_REQUIRED, task.status().state());
        assertEquals("plan_approval",
                ((Map<?, ?>) task.metadata().get("mailbus")).get("hqType"));

        A2AError miss = assertThrows(A2AError.class,
                () -> bridge.onGetTask(new TaskQueryParams("nope"), null));
        assertEquals(-32001, miss.getCode());
    }

    @Test
    void cancelTaskCancelsMailbusTask() throws Exception {
        bridge.onMessageSend(sendParams("ext-sdk-cancel"), null);
        Task task = bridge.onCancelTask(new CancelTaskParams("ext-sdk-cancel"), null);
        assertEquals(TaskState.TASK_STATE_CANCELED, task.status().state());
        assertEquals("cancelled",
                ((Map<?, ?>) repo.find("ext-sdk-cancel").orElseThrow().get("fsm")).get("state"));
    }

    @Test
    void listTasksReturnsAll() throws Exception {
        bridge.onMessageSend(sendParams("ext-sdk-list"), null);
        var out = bridge.onListTasks(null, null);
        assertEquals(1, out.tasks().size());
        assertEquals("ext-sdk-list", out.tasks().get(0).id());
    }

    @Test
    void unsupportedFacesThrowMinus32601() {
        A2AError e = assertThrows(A2AError.class,
                () -> bridge.onSubscribeToTask(null, null));
        assertEquals(-32601, e.getCode());
    }

    @Test
    void messageStreamPushesStatesUntilTerminal() throws Exception {
        // M 级待批任务：working → input-required 帧；外部 cancel 后 canceled 终帧 + 关流
        Flow.Publisher<StreamingEventKind> pub =
                bridge.onMessageSendStream(sendParams("ext-sdk-stream"), null);

        List<String> states = new CopyOnWriteArrayList<>();
        CompletableFuture<Void> done = new CompletableFuture<>();
        pub.subscribe(new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription s) {
                s.request(Long.MAX_VALUE);
            }

            @Override
            public void onNext(StreamingEventKind event) {
                if (event instanceof org.a2aproject.sdk.spec.TaskStatusUpdateEvent ev) {
                    states.add(ev.status().state().name());
                }
            }

            @Override
            public void onError(Throwable t) {
                done.completeExceptionally(t);
            }

            @Override
            public void onComplete() {
                done.complete(null);
            }
        });

        // 等 input-required 帧到位后触发终态
        for (int i = 0; i < 40 && states.size() < 2; i++) {
            Thread.sleep(100);
        }
        bridge.onCancelTask(new CancelTaskParams("ext-sdk-stream"), null);
        done.get(10, TimeUnit.SECONDS);

        assertTrue(states.contains(TaskState.TASK_STATE_WORKING.name()), "states=" + states);
        assertTrue(states.contains(TaskState.TASK_STATE_INPUT_REQUIRED.name()), "states=" + states);
        assertEquals(TaskState.TASK_STATE_CANCELED.name(), states.get(states.size() - 1));
    }
}
