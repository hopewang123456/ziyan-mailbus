package io.github.hopewang123456.mailbus.app;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * A2A JSON-RPC 客户端 — python {@code HttpA2AClient._rpc/send_message} 对等
 * （M2d-a 对角互操作：java 作 client 调 python server）。请求/响应形状与
 * python 逐字对齐：POST {jsonrpc,id,method,params} → {jsonrpc,id,result|error}。
 */
public class HttpA2AClient {

    /** python NonRetryable/Retryable 分类对齐的可重试错误码。 */
    public static class A2aTransportException extends RuntimeException {
        public final boolean retryable;

        public A2aTransportException(String message, boolean retryable) {
            super(message);
            this.retryable = retryable;
        }
    }

    private final HttpClient http;
    private final String rpcUrl;

    public HttpA2AClient(String baseUrl, String agentId) {
        this(baseUrl, agentId, Duration.ofSeconds(30));
    }

    public HttpA2AClient(String baseUrl, String agentId, Duration timeout) {
        this.rpcUrl = baseUrl.replaceAll("/$", "") + "/api/a2a/rpc/" + agentId;
        this.http = HttpClient.newBuilder().connectTimeout(timeout).build();
    }

    /** canonical dispatch → SendMessage；返回 wire task。 */
    public Map<String, Object> sendMessage(String intent, String mailbusTaskId, String stepId) {
        Map<String, Object> mailbus = new LinkedHashMap<>();
        mailbus.put("taskId", mailbusTaskId);
        if (stepId != null) {
            mailbus.put("stepId", stepId);
        }
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("messageId", UUID.randomUUID().toString());
        message.put("role", "ROLE_USER");
        message.put("parts", java.util.List.of(Map.of("text", intent)));
        message.put("metadata", Map.of("mailbus", mailbus));
        Map<String, Object> result = rpc("SendMessage", Map.of("message", message));
        return result.get("task") instanceof Map<?, ?> t ? (Map<String, Object>) t : Map.of();
    }

    public Map<String, Object> getTask(String taskId) {
        return rpc("GetTask", Map.of("id", taskId));
    }

    public Map<String, Object> cancelTask(String taskId) {
        return rpc("CancelTask", Map.of("id", taskId));
    }

    private Map<String, Object> rpc(String method, Map<String, Object> params) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("jsonrpc", "2.0");
        payload.put("id", UUID.randomUUID().toString());
        payload.put("method", method);
        payload.put("params", params);
        HttpRequest req;
        try {
            req = HttpRequest.newBuilder(URI.create(rpcUrl))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(payload)))
                    .build();
        } catch (IOException e) {
            throw new A2aTransportException("serialize_failed: " + e.getMessage(), false);
        }
        HttpResponse<String> resp;
        try {
            resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        } catch (IOException e) {
            throw new A2aTransportException("network: " + e.getMessage(), true);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new A2aTransportException("interrupted", false);
        }
        Map<String, Object> doc;
        try {
            doc = new com.fasterxml.jackson.databind.ObjectMapper().readValue(resp.body(),
                    new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {
                    });
        } catch (IOException e) {
            throw new A2aTransportException("invalid_json_response", false);
        }
        if (doc.get("error") instanceof Map<?, ?> err) {
            String code = String.valueOf(err.get("code"));
            String msg = String.valueOf(err.get("message"));
            boolean retryable = "-32603".equals(code) || "503".equals(code) || "504".equals(code)
                    || msg.toLowerCase().contains("timeout");
            throw new A2aTransportException(msg, retryable);
        }
        return doc.get("result") instanceof Map<?, ?> r ? (Map<String, Object>) r : Map.of();
    }
}
