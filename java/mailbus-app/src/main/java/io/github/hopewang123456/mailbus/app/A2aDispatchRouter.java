package io.github.hopewang123456.mailbus.app;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A2A transport_router 派发通道（M2d-b2b）— python
 * {@code core/a2a/router.py TransportRouter.dispatch_step} 对等（核心语义）：
 * agent 配置了远端 endpoint 且未显式 local_cli/human/disabled 时，步骤经
 * HttpA2AClient 远端派发（step 落 transport_used=a2a_standard + a2a_task_id）；
 * 失败回落调用方 file 派发（python file_bus 兜底同语义）。
 *
 * <p>显式偏差（登记）：python can_deliver_a2a 还看 agent_card/interfaces 多源
 * （依赖 agent-channels.json 全机制），java 第一版以 endpoint 显式配置为准；
 * a2a 重试退避（max_retries/backoff）第一版单次尝试，HttpA2AClient 内建
 * retryable 分类不变。
 */
public final class A2aDispatchRouter {

    private final Map<String, Object> config;

    public A2aDispatchRouter(Map<String, Object> config) {
        this.config = config == null ? Map.of() : config;
    }

    /** transport.use_router 开关（python transport_router_enabled 对等）。 */
    public boolean enabled() {
        return Boolean.TRUE.equals(((Map<?, ?>) config.getOrDefault("transport", Map.of())).get("use_router"));
    }

    /** python can_deliver_a2a 核心语义（endpoint 显式为准）。 */
    public boolean canDeliverA2a(String agentId, Map<String, Object> agentsConfig) {
        if (agentId == null || agentId.isEmpty()) {
            return false;
        }
        Map<String, Object> cfg = agentsConfig == null ? Map.of() : toMap(agentsConfig.get(agentId));
        if ("local_cli".equals(str(cfg.get("transport")))) {
            return false;
        }
        if ("human".equals(str(cfg.get("runtime")))) {
            return false;
        }
        Map<String, Object> channels = toMap(cfg.get("channels"));
        Map<String, Object> a2aCh = toMap(channels.get("a2a"));
        if (Boolean.FALSE.equals(a2aCh.get("enabled")) || Boolean.FALSE.equals(a2aCh.get("available"))) {
            return false;
        }
        Map<String, Object> endpoint = toMap(cfg.get("endpoint"));
        return !str(endpoint.get("base_url")).isEmpty() || !str(endpoint.get("rpc_url")).isEmpty();
    }

    /** 派发结果：ok=true 远端成功（step 已标记）；fallback=true 需调用方走 file 派发。 */
    public record Outcome(boolean ok, boolean fallback, String transportUsed,
                          String a2aTaskId, String error, Map<String, Object> attempt) {
    }

    /**
     * 尝试远端派发一步。不修改任务文件（step 变更由调用方落盘）；
     * ok=false 且 fallback=true 时调用方继续 file 派发。
     */
    public Outcome tryDispatch(Map<String, Object> task, Map<String, Object> step,
                               Map<String, Object> agentsConfig, String summary) {
        String toAgent = firstNonEmpty(step.get("to_agent"), step.get("to_person"));
        String taskId = str(task.getOrDefault("task_id", task.get("id")));
        String stepId = str(step.getOrDefault("step_id", "s" + step.get("step")));
        if (!enabled() || !canDeliverA2a(toAgent, agentsConfig)) {
            return new Outcome(false, true, "file_bus", null, null, null);
        }
        Map<String, Object> cfg = toMap(agentsConfig.get(toAgent));
        Map<String, Object> endpoint = toMap(cfg.get("endpoint"));
        String url = str(endpoint.get("rpc_url"));
        if (url.isEmpty()) {
            url = str(endpoint.get("base_url")).replaceAll("/+$", "") + "/api/a2a/rpc/" + toAgent;
        }
        Map<String, Object> attempt = new LinkedHashMap<>();
        attempt.put("channel", "a2a_standard");
        attempt.put("url", url);
        try {
            HttpA2AClient client = new HttpA2AClient(url, toAgent, Duration.ofSeconds(15));
            Map<String, Object> wire = client.sendMessage(summary == null || summary.isEmpty()
                    ? "mailbus step dispatch" : summary, taskId, stepId);
            String a2aTaskId = str(wire.get("id"));
            // step 审计字段（python persist_step_transport 同键）
            List<Map<String, Object>> attempts = new ArrayList<>();
            attempt.put("ok", true);
            attempt.put("a2a_task_id", a2aTaskId);
            attempts.add(attempt);
            step.put("transport_used", "a2a_standard");
            step.put("transport_attempts", attempts);
            step.put("a2a_task_id", a2aTaskId);
            return new Outcome(true, false, "a2a_standard", a2aTaskId, null, attempt);
        } catch (RuntimeException e) {
            attempt.put("ok", false);
            attempt.put("error", String.valueOf(e.getMessage()));
            return new Outcome(false, true, "file_bus", null, String.valueOf(e.getMessage()), attempt);
        }
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
