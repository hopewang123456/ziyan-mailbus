package io.github.hopewang123456.mailbus.api;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import io.github.hopewang123456.mailbus.app.A2aSdkBridge;
import io.github.hopewang123456.mailbus.app.HumanQueueService;
import io.github.hopewang123456.mailbus.app.TaskService;
import io.github.hopewang123456.mailbus.ports.TaskRepository;
import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.jsonrpc.common.wrappers.GetTaskRequest;
import org.a2aproject.sdk.jsonrpc.common.wrappers.SendMessageRequest;
import org.a2aproject.sdk.jsonrpc.common.wrappers.SendStreamingMessageRequest;
import org.a2aproject.sdk.spec.A2AError;
import org.a2aproject.sdk.spec.StreamingEventKind;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Flow;
import java.util.concurrent.Semaphore;

/**
 * A2A 官方 SDK 面（M2d-b1）— RequestHandler SPI 桥 + SDK wrapper 编解码。
 *
 * <p>wire 方法名与既有 0.2 面（POST /api/a2a/rpc/{agent}）同名同协议
 * （SDK 1.4.0.Final 的 A2AMethods 即 SendMessage/GetTask/…PascalCase），
 * 另接受 0.3 kebab 别名（message/send 等，与 python 侧 alias 对等归一）。
 * 本面增值：SDK 类型校验（messageId 必填等）、ListTasks、流式由 SDK publisher 驱动。
 *
 * <p>JSON-RPC 编解码直接走 SDK JsonUtil（Gson）；桥 {@link A2aSdkBridge}
 * 复用 TaskService 创建/取消链路。SSE 走独立 8 连接护栏（与 StreamController
 * 语义一致，后续统一全局池时合并）。
 */
@RestController
public class A2aSdkController {

    private static final int MAX_STREAMS = 8;
    private final Semaphore streamPermits = new Semaphore(MAX_STREAMS);

    private final TaskService tasks;
    private final TaskRepository repo;
    private final HumanQueueService humanQueue;

    public A2aSdkController(TaskService tasks, TaskRepository repo,
                            org.springframework.core.env.Environment env, java.time.Clock clock) {
        this.tasks = tasks;
        this.repo = repo;
        // 轻量只读对象内 new（boot 装配先例；HumanQueueService 无状态、幂等读文件）
        var dir = io.github.hopewang123456.mailbus.app.SharedRoots.resolveDataDir(
                env.getProperty("mailbus.data-dir"));
        this.humanQueue = new HumanQueueService(dir, clock);
    }

    /** 0.3 kebab 别名 → SDK wrapper 期望的 PascalCase（双名兼容，归一后统一解码）。 */
    private static final Map<String, String> METHOD_ALIASES = Map.of(
            "message/send", "SendMessage",
            "message/stream", "SendStreamingMessage",
            "tasks/get", "GetTask",
            "tasks/cancel", "CancelTask",
            "tasks/list", "ListTasks");

    @PostMapping(value = "/api/a2a/sdk/{agent}")
    public Object rpc(@PathVariable("agent") String agent, @RequestBody String raw) {
        JsonObject body;
        String method;
        Object rpcId;
        String normalized;
        try {
            body = JsonParser.parseString(raw).getAsJsonObject();
            method = body.has("method") && !body.get("method").isJsonNull()
                    ? body.get("method").getAsString() : "";
            rpcId = body.has("id") && !body.get("id").isJsonNull() ? gsonToPlain(body.get("id")) : null;
            normalized = METHOD_ALIASES.getOrDefault(method, method);
            if (!normalized.equals(method)) {
                body.addProperty("method", normalized);
                raw = body.toString();
            }
        } catch (RuntimeException e) {
            return ResponseEntity.badRequest().body(json(errorDoc(null, -32700, "parse error")));
        }

        A2aSdkBridge bridge = new A2aSdkBridge(agent, tasks, repo, humanQueue);
        try {
            switch (normalized) {
                case "SendMessage" -> {
                    SendMessageRequest req = JsonUtil.fromJson(raw, SendMessageRequest.class);
                    Object result = bridge.onMessageSend(req.getParams(), null);
                    return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON)
                            .body(json(resultDoc(rpcId, result)));
                }
                case "GetTask" -> {
                    GetTaskRequest req = JsonUtil.fromJson(raw, GetTaskRequest.class);
                    Object result = bridge.onGetTask(req.getParams(), null);
                    return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON)
                            .body(json(resultDoc(rpcId, result)));
                }
                case "CancelTask" -> {
                    // CancelTaskParams 三参 canonical 构造含 @NonNull 校验，Gson 直解会炸——手动取 id
                    String tid = body.has("params") && body.getAsJsonObject("params").has("id")
                            && !body.getAsJsonObject("params").get("id").isJsonNull()
                            ? body.getAsJsonObject("params").get("id").getAsString() : "";
                    Object result = bridge.onCancelTask(
                            new org.a2aproject.sdk.spec.CancelTaskParams(tid), null);
                    return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON)
                            .body(json(resultDoc(rpcId, result)));
                }
                case "ListTasks" -> {
                    // ListTasksParams 含 Instant 字段，SDK Gson 未配 adapter——本面忽略过滤参数，全量列出
                    Object result = bridge.onListTasks(null, null);
                    return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON)
                            .body(json(resultDoc(rpcId, result)));
                }
                case "SendStreamingMessage" -> {
                    SendStreamingMessageRequest req =
                            JsonUtil.fromJson(raw, SendStreamingMessageRequest.class);
                    return stream(agent, rpcId, bridge.onMessageSendStream(req.getParams(), null));
                }
                default -> {
                    return ResponseEntity.status(404).contentType(MediaType.APPLICATION_JSON)
                            .body(json(errorDoc(rpcId, -32601, "method not found: " + method)));
                }
            }
        } catch (A2AError e) {
            int http = e.getCode() != null && e.getCode() == -32001 ? 404 : 400;
            return ResponseEntity.status(http).contentType(MediaType.APPLICATION_JSON)
                    .body(json(errorDoc(rpcId, e.getCode() == null ? -32000 : e.getCode(),
                            String.valueOf(e.getMessage()))));
        } catch (RuntimeException e) {
            // SDK 反序列化/校验失败（如缺 messageId）→ invalid params，与 JSON-RPC 惯例一致
            return ResponseEntity.status(400).contentType(MediaType.APPLICATION_JSON)
                    .body(json(errorDoc(rpcId, -32602, "invalid params: " + e.getMessage())));
        } catch (Exception e) {
            return ResponseEntity.status(500).contentType(MediaType.APPLICATION_JSON)
                    .body(json(errorDoc(rpcId, -32603, "internal: " + e.getMessage())));
        }
    }

    /** message/stream：订阅 SDK publisher，每帧包 JSON-RPC response 推 SSE。 */
    private SseEmitter stream(String agent, Object rpcId, Flow.Publisher<StreamingEventKind> publisher) {
        if (!streamPermits.tryAcquire()) {
            throw new StreamController.StreamLimitException(
                    "too many concurrent a2a streams (limit " + MAX_STREAMS + ")");
        }
        SseEmitter emitter = new SseEmitter(0L); // 无容器超时；bridge 内 120s 兜底
        emitter.onCompletion(streamPermits::release);
        emitter.onTimeout(streamPermits::release);
        emitter.onError(e -> streamPermits.release());
        publisher.subscribe(new Flow.Subscriber<>() {
            private Flow.Subscription sub;

            @Override
            public void onSubscribe(Flow.Subscription s) {
                this.sub = s;
                s.request(Long.MAX_VALUE);
            }

            @Override
            public void onNext(StreamingEventKind event) {
                try {
                    emitter.send(SseEmitter.event().data(json(resultDoc(rpcId, event)),
                            MediaType.APPLICATION_JSON));
                } catch (IOException | IllegalStateException e) {
                    if (sub != null) {
                        sub.cancel();
                    }
                }
            }

            @Override
            public void onError(Throwable t) {
                try {
                    emitter.send(SseEmitter.event().data(
                            json(errorDoc(rpcId, -32603, String.valueOf(t.getMessage()))),
                            MediaType.APPLICATION_JSON));
                } catch (IOException ignored) {
                    // client gone
                }
                emitter.complete();
            }

            @Override
            public void onComplete() {
                emitter.complete();
            }
        });
        return emitter;
    }

    private static Map<String, Object> resultDoc(Object rpcId, Object result) {
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("jsonrpc", "2.0");
        doc.put("id", rpcId);
        doc.put("result", result);
        return doc;
    }

    private static Map<String, Object> errorDoc(Object rpcId, int code, String message) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("code", code);
        err.put("message", message == null || message.isEmpty() ? "rpc_error" : message);
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("jsonrpc", "2.0");
        doc.put("id", rpcId);
        doc.put("error", err);
        return doc;
    }

    /** Gson JsonPrimitive → plain Java（Long/Double/String/Boolean），供 id 透传。 */
    private static Object gsonToPlain(com.google.gson.JsonElement el) {
        if (el == null || el.isJsonNull()) {
            return null;
        }
        if (el.isJsonPrimitive()) {
            var p = el.getAsJsonPrimitive();
            if (p.isNumber()) {
                return p.getAsNumber().longValue();
            }
            if (p.isBoolean()) {
                return p.getAsBoolean();
            }
            return p.getAsString();
        }
        return el.toString();
    }

    private static String json(Object doc) {
        try {
            return JsonUtil.toJson(doc);
        } catch (Exception e) {
            return "{\"jsonrpc\":\"2.0\",\"id\":null,\"error\":{\"code\":-32603,\"message\":\"encode failed\"}}";
        }
    }
}
