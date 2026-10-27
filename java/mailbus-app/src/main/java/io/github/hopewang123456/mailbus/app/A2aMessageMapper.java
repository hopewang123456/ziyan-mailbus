package io.github.hopewang123456.mailbus.app;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A2A 消息映射 — python {@code a2a_mapper.from_a2a_task_create} 对等（M2d-a）：
 * Google A2A SendMessage params → mailbus A2A Envelope；wire Task 形状。
 */
public final class A2aMessageMapper {

    private A2aMessageMapper() {
    }

    /** SendMessage params → envelope（python 同字段语义；task_id 缺省 ext- 前缀）。 */
    public static Map<String, Object> fromA2aTaskCreate(Map<String, Object> params) {
        Map<String, Object> message;
        if (params.get("message") instanceof Map<?, ?> m) {
            message = toMap(m);
        } else {
            message = params;
        }
        Map<String, Object> meta = Map.of();
        if (message.get("metadata") instanceof Map<?, ?> mm && mm.get("mailbus") instanceof Map<?, ?> mmMail) {
            meta = toMap(mmMail);
        }
        List<Object> parts;
        if (message.get("parts") instanceof List<?> l) {
            parts = new ArrayList<>(l);
        } else {
            parts = List.of();
        }

        StringBuilder intent = new StringBuilder();
        List<Object> artifactsIn = new ArrayList<>();
        for (Object p : parts) {
            if (!(p instanceof Map<?, ?> part)) {
                continue;
            }
            if (part.get("text") != null) {
                intent.append(intent.isEmpty() ? "" : "\n").append(String.valueOf(part.get("text")));
            } else if (part.get("file") instanceof Map<?, ?> file && file.get("uri") != null) {
                Object mime = file.get("mimeType");
                artifactsIn.add(Map.of("uri", String.valueOf(file.get("uri")),
                        "mime_type", mime == null ? "application/octet-stream" : String.valueOf(mime)));
            }
        }

        String taskId = firstNonEmpty(meta.get("taskId"), meta.get("task_id"), params.get("task_id"));
        if (taskId.isEmpty()) {
            taskId = "ext-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        }
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("task_id", taskId);
        envelope.put("intent", intent.isEmpty() ? firstNonEmpty(meta.get("intent"), "external A2A task") : intent.toString());
        envelope.put("initiator", firstNonEmpty(meta.get("initiator"), "external"));
        envelope.put("task_type", firstNonEmpty(meta.get("taskType"), meta.get("task_type"), "custom"));
        envelope.put("tier", firstNonEmpty(meta.get("tier"), "M"));
        envelope.put("mode", firstNonEmpty(meta.get("mode"), "auto"));
        envelope.put("artifacts_in", artifactsIn);
        envelope.put("extensions", meta.get("extensions") instanceof Map<?, ?> e ? toMap(e) : Map.of());
        if (meta.get("planned_chain") instanceof List<?> planned) {
            envelope.put("mode", "explicit");
            envelope.put("planned_chain", planned);
        }
        if (meta.get("constraints") instanceof Map<?, ?> c) {
            envelope.put("constraints", toMap(c));
        }
        return envelope;
    }

    /** wire Task（python _create_a2a_wire_task 形状）。 */
    public static Map<String, Object> wireTask(String taskId, String stepId) {
        Map<String, Object> mailbus = new LinkedHashMap<>();
        mailbus.put("taskId", taskId);
        if (stepId != null && !stepId.isEmpty()) {
            mailbus.put("stepId", stepId);
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mailbus", mailbus);
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("id", taskId);
        task.put("status", "working");
        task.put("metadata", metadata);
        return task;
    }

    /**
     * GetTask 富 wire — python {@code to_a2a_hub_task} 对等（M2d-b1）：
     * fsm→A2A 状态映射 + pending human-queue 上下文（input-required 及其标题）。
     */
    public static Map<String, Object> hubTask(Map<String, Object> taskDoc, String a2aTaskId,
                                              List<Map<String, Object>> humanQueue) {
        Map<String, Object> fsm = taskDoc.get("fsm") instanceof Map<?, ?> f ? toMap(f) : Map.of();
        String fsmState = strOrDefault(fsm.get("state"), "executing");
        String taskId = firstNonEmpty(taskDoc.get("task_id"), taskDoc.get("id"));

        Map<String, Object> mailbus = new LinkedHashMap<>();
        mailbus.put("taskId", taskId);
        mailbus.put("taskType", taskDoc.get("task_type"));
        mailbus.put("tier", taskDoc.get("tier"));
        mailbus.put("fsmState", fsmState);
        mailbus.put("protocolVersion", "mailbus-a2a/1");

        String status = "working";
        String statusMessage = firstNonEmpty(taskDoc.get("intent"));

        Map<String, Object> pendingHq = null;
        for (Map<String, Object> item : humanQueue) {
            if (!"pending".equals(strOrDefault(item.get("status"), ""))) {
                continue;
            }
            if (!taskId.equals(strOrDefault(item.get("task_id"), ""))) {
                continue;
            }
            String t = strOrDefault(item.get("type"), "");
            if (t.equals("a2a_input_required") || t.equals("final_acceptance") || t.equals("plan_approval")) {
                pendingHq = item;
                break;
            }
        }

        if (pendingHq != null) {
            status = "input-required";
            statusMessage = firstNonEmpty(pendingHq.get("title"), statusMessage);
            mailbus.put("hqType", pendingHq.get("type"));
            mailbus.put("hqId", pendingHq.get("id"));
            Object prompt = pendingHq.get("context") instanceof Map<?, ?> ctx ? ctx.get("prompt") : null;
            if (prompt != null && !String.valueOf(prompt).isEmpty()) {
                statusMessage = String.valueOf(prompt);
            }
        } else if ("accepting".equals(fsmState)) {
            status = "input-required";
            statusMessage = "等待终验确认";
            mailbus.put("hqType", "final_acceptance");
        } else if ("blocked".equals(fsmState) || "paused".equals(fsmState)) {
            status = "input-required";
            statusMessage = firstNonEmpty(taskDoc.get("pause_reason"), taskDoc.get("error"), "blocked");
        } else if ("succeeded".equals(fsmState) || "success".equals(fsmState)) {
            status = "completed";
        } else if ("failed".equals(fsmState)) {
            status = "failed";
        } else if ("cancelled".equals(fsmState)) {
            status = "canceled";
        }

        // 首个活跃步骤的 stepId / a2a_task_id
        if (taskDoc.get("chain") instanceof List<?> chain) {
            for (Object o : chain) {
                if (!(o instanceof Map<?, ?> step)) {
                    continue;
                }
                String fs = strOrDefault(step.get("fsm_state"), "");
                if (fs.equals("queued") || fs.equals("running") || fs.equals("dispatched") || fs.equals("working")) {
                    if (step.get("step_id") != null) {
                        mailbus.put("stepId", step.get("step_id"));
                    }
                    if (step.get("a2a_task_id") != null) {
                        a2aTaskId = String.valueOf(step.get("a2a_task_id"));
                    }
                    break;
                }
            }
        }

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mailbus", mailbus);
        Map<String, Object> wire = new LinkedHashMap<>();
        wire.put("id", a2aTaskId == null || a2aTaskId.isEmpty() ? taskId : a2aTaskId);
        wire.put("status", status);
        wire.put("metadata", metadata);
        if (!statusMessage.isEmpty()) {
            wire.put("statusMessage", statusMessage);
        }
        return wire;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object o) {
        return (Map<String, Object>) o;
    }

    private static String firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return String.valueOf(v);
            }
        }
        return "";
    }

    private static String strOrDefault(Object o, String fallback) {
        return o == null || String.valueOf(o).isEmpty() ? fallback : String.valueOf(o);
    }
}
