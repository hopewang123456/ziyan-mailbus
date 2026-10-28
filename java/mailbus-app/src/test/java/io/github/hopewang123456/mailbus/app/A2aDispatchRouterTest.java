package io.github.hopewang123456.mailbus.app;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2d-b2b transport_router — can_deliver 判定矩阵 + 远端派发/回落
 * （python TransportRouter.dispatch_step 核心语义对等）。
 */
class A2aDispatchRouterTest {

    private HttpServer fake;

    @AfterEach
    void tearDown() {
        if (fake != null) {
            fake.stop(0);
        }
    }

    private String startFake(String resultJson) throws IOException {
        fake = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        fake.createContext("/", exchange -> {
            byte[] body = resultJson.getBytes();
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        fake.start();
        return "http://127.0.0.1:" + fake.getAddress().getPort();
    }

    @Test
    void canDeliverMatrix() {
        A2aDispatchRouter r = new A2aDispatchRouter(Map.of("transport", Map.of("use_router", true)));
        assertFalse(r.canDeliverA2a("", Map.of()));
        assertFalse(r.canDeliverA2a("a", Map.of("a", Map.of("transport", "local_cli"))));
        assertFalse(r.canDeliverA2a("a", Map.of("a", Map.of("runtime", "human"))));
        assertFalse(r.canDeliverA2a("a", Map.of("a",
                Map.of("channels", Map.of("a2a", Map.of("enabled", false))))));
        assertFalse(r.canDeliverA2a("a", Map.of("a", Map.of()))); // 无 endpoint
        assertTrue(r.canDeliverA2a("a", Map.of("a",
                Map.of("endpoint", Map.of("base_url", "http://x")))));
        assertTrue(r.canDeliverA2a("a", Map.of("a",
                Map.of("endpoint", Map.of("rpc_url", "http://x/rpc")))));
    }

    @Test
    void routerDisabledFallsBackToFile() {
        A2aDispatchRouter r = new A2aDispatchRouter(Map.of());
        var out = r.tryDispatch(Map.of("task_id", "t1"),
                Map.of("step_id", "s1", "to_agent", "a"), Map.of(), "x");
        assertFalse(out.ok());
        assertTrue(out.fallback());
        assertEquals("file_bus", out.transportUsed());
    }

    @Test
    void remoteDispatchMarksStep() throws IOException {
        String url = startFake(
                "{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"task\":{\"id\":\"remote-42\",\"status\":\"working\"}}}");
        A2aDispatchRouter r = new A2aDispatchRouter(Map.of("transport", Map.of("use_router", true)));
        Map<String, Object> step = new java.util.LinkedHashMap<>(
                Map.of("step_id", "s1", "to_agent", "remoteAgent"));
        var out = r.tryDispatch(Map.of("task_id", "t1"), step, Map.of("remoteAgent",
                Map.of("endpoint", Map.of("base_url", url))), "远端派发测试");
        assertTrue(out.ok());
        assertEquals("remote-42", out.a2aTaskId());
        assertEquals("a2a_standard", step.get("transport_used"));
        assertEquals("remote-42", step.get("a2a_task_id"));
        List<?> attempts = (List<?>) step.get("transport_attempts");
        assertEquals(1, attempts.size());
    }

    @Test
    void remoteFailureFallsBackWithAttemptAudit() throws IOException {
        // 端口立即关停 → 连接拒绝
        String url = startFake("{}");
        fake.stop(0);
        fake = null;
        A2aDispatchRouter r = new A2aDispatchRouter(Map.of("transport", Map.of("use_router", true)));
        Map<String, Object> step = new java.util.LinkedHashMap<>(
                Map.of("step_id", "s1", "to_agent", "remoteAgent"));
        var out = r.tryDispatch(Map.of("task_id", "t1"), step, Map.of("remoteAgent",
                Map.of("endpoint", Map.of("rpc_url", url))), "x");
        assertFalse(out.ok());
        assertTrue(out.fallback());
        assertNull(out.a2aTaskId());
        assertTrue(out.attempt() != null && Boolean.FALSE.equals(out.attempt().get("ok")));
    }
}
