package io.github.hopewang123456.mailbus.collab;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.stream.StreamGate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

/** 大屏 SSE：进程内广播，可按 screen_id 过滤。 */
@Service
public class CollabStreamService {

    /** 公开流事件白名单：未列出的事件直接丢弃，避免新增事件意外泄露。 */
    private static final Map<String, Set<String>> PUBLIC_FIELDS = Map.of(
            "pair.started", Set.of("pair_id", "at"),
            "pair.ended", Set.of("pair_id", "at"),
            "message.created", Set.of("message_id", "pair_id", "kind", "body", "created_at"),
            "task.updated", Set.of("seat_id", "title", "state", "current_node",
                    "node_state", "progress_done", "progress_total", "updated_at"),
            "screen.config", Set.of("screen_id", "config_version", "at"),
            "screen.focus", Set.of("screen_id", "floor_id", "seat_id", "at"));

    private final List<Subscriber> subscribers = new CopyOnWriteArrayList<>();
    private final ObjectMapper objectMapper;
    private final StreamGate gate;

    public CollabStreamService(ObjectMapper objectMapper, StreamGate gate) {
        this.objectMapper = objectMapper;
        this.gate = gate;
    }

    public SseEmitter subscribe(String screenId) {
        return subscribe(screenId, false);
    }

    public SseEmitter subscribe(String screenId, boolean publicStream) {
        if (!gate.acquire()) {
            throw ApiException.capacityExceeded("大屏连接数已达上限，请稍后重试");
        }
        SseEmitter emitter = new SseEmitter(0L);
        Subscriber subscriber = new Subscriber(emitter, screenId, publicStream);
        emitter.onCompletion(() -> close(subscriber));
        emitter.onTimeout(() -> close(subscriber));
        emitter.onError(error -> close(subscriber));
        subscribers.add(subscriber);
        try {
            emitter.send(SseEmitter.event().comment("connected"));
        } catch (Exception exception) {
            close(subscriber);
        }
        return emitter;
    }

    public void publish(String event, Map<String, Object> payload) {
        if (subscribers.isEmpty()) {
            return;
        }
        Map<String, Object> publicPayload = scrub(event, payload);
        String data;
        String publicData;
        try {
            data = objectMapper.writeValueAsString(payload);
            publicData = publicPayload == null ? null
                    : objectMapper.writeValueAsString(publicPayload);
        } catch (Exception exception) {
            return;
        }
        for (Subscriber subscriber : subscribers) {
            if (!matches(subscriber.screenId(), payload)) {
                continue;
            }
            String body = subscriber.publicStream() ? publicData : data;
            if (body == null) {
                continue;
            }
            try {
                subscriber.emitter().send(SseEmitter.event().name(event).data(body));
            } catch (Exception exception) {
                remove(subscriber);
            }
        }
    }

    private static Map<String, Object> scrub(String event, Map<String, Object> payload) {
        Set<String> fields = PUBLIC_FIELDS.get(event);
        if (fields == null) {
            return null;
        }
        Map<String, Object> scrubbed = new LinkedHashMap<>();
        for (String field : fields) {
            if (payload.containsKey(field)) {
                scrubbed.put(field, payload.get(field));
            }
        }
        return scrubbed;
    }

    @Scheduled(fixedDelayString = "${mailbus.stream-interval-ms:15000}")
    public void heartbeat() {
        for (Subscriber subscriber : subscribers) {
            try {
                subscriber.emitter().send(SseEmitter.event().comment("ping"));
            } catch (Exception exception) {
                remove(subscriber);
            }
        }
    }

    private boolean matches(String screenId, Map<String, Object> payload) {
        return screenId == null || screenId.equals(payload.get("screen_id"));
    }

    private void close(Subscriber subscriber) {
        if (subscribers.remove(subscriber)) {
            gate.release();
        }
    }

    private void remove(Subscriber subscriber) {
        close(subscriber);
        try {
            subscriber.emitter().complete();
        } catch (Exception ignored) {
            // 连接已断开
        }
    }

    private record Subscriber(SseEmitter emitter, String screenId, boolean publicStream) {
    }
}
