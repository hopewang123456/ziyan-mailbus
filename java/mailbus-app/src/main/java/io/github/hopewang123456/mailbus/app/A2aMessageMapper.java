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
}
