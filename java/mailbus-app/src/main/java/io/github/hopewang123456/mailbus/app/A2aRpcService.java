package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A2A 入站代理 — python {@code handlers_a2a.handle_a2a_rpc} 对等（M2d-a）：
 * JSON-RPC 2.0（SendMessage → 建任务（与 M2a 同一创建链路）；GetTask → 任务池
 * 查询；CancelTask → 既有 cancel 动作）。SendStreamingMessage/SSE 属 M2d-b。
 */
public class A2aRpcService {

    private final Path dataDir;
    private final TaskService tasks;
    private final TaskRepository repo;
    private final HumanQueueService humanQueue;

    public A2aRpcService(Path dataDir, TaskService tasks, TaskRepository repo,
                         HumanQueueService humanQueue) {
        this.dataDir = dataDir;
        this.tasks = tasks;
        this.repo = repo;
        this.humanQueue = humanQueue;
    }

    /** 返回 {status, body}；body 为 JSON-RPC 响应文档。 */
    public Map<String, Object> rpc(String agentId, Map<String, Object> body) {
        String method = str(body.get("method"));
        Object rpcId = body.get("id");
        Map<String, Object> params = body.get("params") instanceof Map<?, ?> p ? toMap(p) : Map.of();

        if ("SendMessage".equals(method)) {
            Map<String, Object> envelope = A2aMessageMapper.fromA2aTaskCreate(params);
            envelope.put("target_agent", agentId); // 审计：入站代理目标
            TaskService.Result r = tasks.createFromEnvelope(envelope);
            if (r.status() == 201) {
                Map<String, Object> task = toMap(r.body().get("task"));
                List<Map<String, Object>> chain = TaskFsmViews.chain(task);
                String stepId = chain.isEmpty() ? null : str(chain.get(0).get("step_id"));
                return result(rpcId, Map.of("task",
                        A2aMessageMapper.wireTask(str(task.get("task_id")), stepId)), 200);
            }
            return error(rpcId, -32602,
                    str(r.body().get("message")) + str(r.body().get("error")), r.status());
        }
        if ("GetTask".equals(method)) {
            String tid = firstNonEmpty(params.get("id"), params.get("taskId"));
            for (Map<String, Object> task : repo.listAll()) {
                boolean match = tid.equals(str(task.get("task_id"))) || tid.equals(str(task.get("id")));
                if (!match) {
                    match = TaskFsmViews.chain(task).stream()
                            .anyMatch(s -> tid.equals(str(s.get("a2a_task_id"))));
                }
                if (match) {
                    // M2d-b1：富 wire（fsm→A2A 状态 + pending hq 上下文，python to_a2a_hub_task 对等）
                    return result(rpcId, Map.of("task",
                            A2aMessageMapper.hubTask(task, tid, humanQueue.items())), 200);
                }
            }
            return error(rpcId, -32001, "task_not_found", 404);
        }
        if ("CancelTask".equals(method)) {
            String tid = firstNonEmpty(params.get("id"));
            for (Map<String, Object> task : repo.listAll()) {
                boolean match = tid.equals(str(task.get("task_id")));
                if (!match) {
                    match = TaskFsmViews.chain(task).stream()
                            .anyMatch(s -> tid.equals(str(s.get("a2a_task_id"))));
                }
                if (match) {
                    tasks.fsmAction(str(task.get("task_id")), "cancel",
                            Map.of("reason", "a2a_cancel"));
                    return result(rpcId, Map.of("id", tid, "cancelled", true), 200);
                }
            }
            return error(rpcId, -32001, "task_not_found", 404);
        }
        return error(rpcId, -32601, "method not found: " + method
                + " (SendStreamingMessage lands with M2d-b)", 400);
    }

    /** GET /api/a2a/agent-cards — java 侧从 config agents 生成简化目录。 */
    public Map<String, Object> agentCards() {
        Map<String, Object> agents = new RoleResolverService(dataDir, repo).agentsConfig();
        List<Map<String, Object>> items = new ArrayList<>();
        for (String agentId : agents.keySet().stream().sorted().toList()) {
            Map<String, Object> cfg = toMap(agents.get(agentId));
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("agent_id", agentId);
            item.put("name", firstNonEmpty(cfg.get("name"), agentId));
            item.put("functional_group", str(cfg.get("functional_group")));
            item.put("runtime", firstNonEmpty(cfg.get("type"), cfg.get("framework"), "mailbus-java"));
            item.put("has_a2a", true);
            items.add(item);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("total", items.size());
        out.put("items", items);
        return out;
    }

    private static Map<String, Object> result(Object rpcId, Map<String, Object> result, int status) {
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("jsonrpc", "2.0");
        doc.put("id", rpcId);
        doc.put("result", result);
        return Map.of("status", status, "body", doc);
    }

    private static Map<String, Object> error(Object rpcId, int code, String message, int status) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("code", code);
        err.put("message", message == null || message.isEmpty() ? "rpc_error" : message);
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("jsonrpc", "2.0");
        doc.put("id", rpcId);
        doc.put("error", err);
        return Map.of("status", status, "body", doc);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object o) {
        return o instanceof Map<?, ?> m ? (Map<String, Object>) m : new LinkedHashMap<>();
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static String firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return String.valueOf(v);
            }
        }
        return "";
    }
}
