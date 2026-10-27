package io.github.hopewang123456.mailbus.app;

import com.sun.net.httpserver.HttpServer;
import io.github.hopewang123456.mailbus.adapters.filestore.FileTaskRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2d-a A2A 对角 — JSON-RPC server 面（SendMessage/GetTask/CancelTask）+
 * HttpA2AClient 请求形状对拍（python HttpA2AClient 协议逐字对齐）。
 */
class A2aRpcShapeTest {

    @TempDir
    Path dataDir;

    private A2aRpcService rpc;
    private FileTaskRepository repo;
    private HttpServer fakeServer;
    private int fakePort;
    private final AtomicReference<String> lastRequest = new AtomicReference<>();
    private final AtomicReference<String> lastUri = new AtomicReference<>();

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
        var taskService = new TaskService(dataDir, clock, repo,
                new RoleResolverService(dataDir, repo),
                new HumanQueueService(dataDir, clock));
        taskService.setPlanner(new TaskPlannerService(dataDir, null));
        rpc = new A2aRpcService(dataDir, taskService, repo);
    }

    @AfterEach
    void tearDown() {
        if (fakeServer != null) {
            fakeServer.stop(0);
        }
    }

    private Map<String, Object> jsonRpc(String method, Map<String, Object> params) {
        return Map.of("jsonrpc", "2.0", "id", "rpc-1", "method", method, "params", params);
    }

    @Test
    void sendMessageCreatesTaskViaM2aPipeline() {
        Map<String, Object> out = rpc.rpc("agentA", jsonRpc("SendMessage", Map.of(
                "message", Map.of(
                        "role", "ROLE_USER",
                        "parts", List.of(Map.of("text", "外部 A2A 需求：修一个 bug")),
                        "metadata", Map.of("mailbus", Map.of(
                                "taskId", "ext-shape-001",
                                "planned_chain", List.of(Map.of("role_type", 1))))))));
        assertEquals(200, ((Number) out.get("status")).intValue());
        Map<?, ?> body = (Map<?, ?>) out.get("body");
        Map<?, ?> task = (Map<?, ?>) ((Map<?, ?>) body.get("result")).get("task");
        assertEquals("ext-shape-001", task.get("id"));
        assertEquals("working", task.get("status")); // 提交即 working（python 同语义）
        assertEquals("ext-shape-001",
                ((Map<?, ?>) ((Map<?, ?>) task.get("metadata")).get("mailbus")).get("taskId"));
        // 走了 M2a 创建链路：任务文件落盘（planned → explicit；tier 默认 M → 待批）
        assertTrue(repo.find("ext-shape-001").isPresent());
        Map<String, Object> saved = repo.find("ext-shape-001").orElseThrow();
        assertEquals("created", ((Map<?, ?>) saved.get("fsm")).get("state"));
    }

    @Test
    void getTaskFindsAndMisses() {
        rpc.rpc("agentA", jsonRpc("SendMessage", Map.of(
                "message", Map.of("parts", List.of(Map.of("text", "x")),
                        "metadata", Map.of("mailbus", Map.of("taskId", "ext-get-1",
                                "planned_chain", List.of(Map.of("role_type", 1))))))));
        Map<String, Object> hit = rpc.rpc("agentA", jsonRpc("GetTask", Map.of("id", "ext-get-1")));
        assertEquals(200, ((Number) hit.get("status")).intValue());

        Map<String, Object> miss = rpc.rpc("agentA", jsonRpc("GetTask", Map.of("id", "nope")));
        assertEquals(404, ((Number) miss.get("status")).intValue());
        assertEquals(-32001.0, ((Number) ((Map<?, ?>) ((Map<?, ?>) miss.get("body")).get("error")).get("code")).doubleValue());
    }

    @Test
    void cancelTaskCancelsMailbusTask() {
        rpc.rpc("agentA", jsonRpc("SendMessage", Map.of(
                "message", Map.of("parts", List.of(Map.of("text", "x")),
                        "metadata", Map.of("mailbus", Map.of("taskId", "ext-cancel-1",
                                "planned_chain", List.of(Map.of("role_type", 1))))))));
        Map<String, Object> out = rpc.rpc("agentA", jsonRpc("CancelTask", Map.of("id", "ext-cancel-1")));
        assertEquals(200, ((Number) out.get("status")).intValue());
        assertEquals(Boolean.TRUE, ((Map<?, ?>) ((Map<?, ?>) out.get("body")).get("result")).get("cancelled"));
        assertEquals("cancelled",
                ((Map<?, ?>) repo.find("ext-cancel-1").orElseThrow().get("fsm")).get("state"));
    }

    @Test
    void unknownMethodGivesMinus32601() {
        Map<String, Object> out = rpc.rpc("agentA", jsonRpc("SendStreamingMessage", Map.of()));
        assertEquals(400, ((Number) out.get("status")).intValue());
        assertEquals(-32601.0,
                ((Number) ((Map<?, ?>) ((Map<?, ?>) out.get("body")).get("error")).get("code")).doubleValue());
    }

    // ── 对角 client：请求形状与 python server 协议对拍（内嵌假 server 断言形状）──

    private void startFakeServer(String respondJson) throws IOException {
        fakeServer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        fakeServer.createContext("/", exchange -> {
            lastUri.set(exchange.getRequestURI().toString());
            lastRequest.set(new String(exchange.getRequestBody().readAllBytes()));
            byte[] body = respondJson.getBytes();
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        fakeServer.start();
        fakePort = fakeServer.getAddress().getPort();
    }

    @Test
    void clientRequestShapeMatchesPythonProtocol() throws IOException {
        startFakeServer("{\"jsonrpc\":\"2.0\",\"id\":\"x\",\"result\":{\"task\":{\"id\":\"wire-1\",\"status\":\"working\"}}}");
        HttpA2AClient client = new HttpA2AClient("http://127.0.0.1:" + fakePort, "agentA");
        Map<String, Object> task = client.sendMessage("对角需求", "t-diag-1", "s1");

        assertEquals("wire-1", task.get("id"));
        // 请求形状：JSON-RPC 2.0 + SendMessage + message{role/parts/metadata.mailbus}
        String sent = lastRequest.get();
        assertTrue(sent.contains("\"method\":\"SendMessage\""));
        assertTrue(sent.contains("\"jsonrpc\":\"2.0\""));
        assertTrue(sent.contains("ROLE_USER"));
        assertTrue(sent.contains("t-diag-1"));
        assertTrue(lastUri.get().contains("/api/a2a/rpc/agentA")); // URL 断言走捕获的请求路径
    }

    @Test
    void clientErrorClassificationAlignsPython() throws IOException {
        startFakeServer("{\"jsonrpc\":\"2.0\",\"id\":\"x\",\"error\":{\"code\":-32603,\"message\":\"boom\"}}");
        HttpA2AClient client = new HttpA2AClient("http://127.0.0.1:" + fakePort, "agentA");
        HttpA2AClient.A2aTransportException e = assertThrows(
                HttpA2AClient.A2aTransportException.class,
                () -> client.sendMessage("x", "t", null));
        assertTrue(e.retryable); // -32603 → retryable（python classify 同）

        startFakeServer("{\"jsonrpc\":\"2.0\",\"id\":\"x\",\"error\":{\"code\":-32001,\"message\":\"task_not_found\"}}");
        HttpA2AClient client2 = new HttpA2AClient("http://127.0.0.1:" + fakePort, "agentA");
        HttpA2AClient.A2aTransportException e2 = assertThrows(
                HttpA2AClient.A2aTransportException.class,
                () -> client2.getTask("nope"));
        assertEquals(false, e2.retryable);
    }
}
