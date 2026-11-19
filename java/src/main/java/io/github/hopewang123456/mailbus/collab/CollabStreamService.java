package io.github.hopewang123456.mailbus.collab;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/** 大屏 SSE：进程内广播，可按 screen_id 过滤。 */
@Service
public class CollabStreamService {

    private final List<Subscriber> subscribers = new CopyOnWriteArrayList<>();
    private final ObjectMapper objectMapper;

    public CollabStreamService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public SseEmitter subscribe(String screenId) {
        SseEmitter emitter = new SseEmitter(0L);
        Subscriber subscriber = new Subscriber(emitter, screenId);
        emitter.onCompletion(() -> subscribers.remove(subscriber));
        emitter.onTimeout(() -> subscribers.remove(subscriber));
        emitter.onError(error -> subscribers.remove(subscriber));
        subscribers.add(subscriber);
        try {
            emitter.send(SseEmitter.event().comment("connected"));
        } catch (Exception exception) {
            subscribers.remove(subscriber);
        }
        return emitter;
    }

    public void publish(String event, Map<String, Object> payload) {
        if (subscribers.isEmpty()) {
            return;
        }
        String data;
        try {
            data = objectMapper.writeValueAsString(payload);
        } catch (Exception exception) {
            return;
        }
        for (Subscriber subscriber : subscribers) {
            if (!matches(subscriber.screenId(), payload)) {
                continue;
            }
            try {
                subscriber.emitter().send(SseEmitter.event().name(event).data(data));
            } catch (Exception exception) {
                remove(subscriber);
            }
        }
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

    private void remove(Subscriber subscriber) {
        subscribers.remove(subscriber);
        try {
            subscriber.emitter().complete();
        } catch (Exception ignored) {
            // 连接已断开
        }
    }

    private record Subscriber(SseEmitter emitter, String screenId) {
    }
}
