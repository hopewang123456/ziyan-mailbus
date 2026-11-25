package io.github.hopewang123456.mailbus.stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.observability.ObservabilityDtos;
import io.github.hopewang123456.mailbus.observability.OverviewService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

@Service
public class StreamService {

    private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();
    private final OverviewService overview;
    private final ObjectMapper objectMapper;
    private final StreamGate gate;
    private volatile String last;

    public StreamService(OverviewService overview, ObjectMapper objectMapper,
                         StreamGate gate) {
        this.overview = overview;
        this.objectMapper = objectMapper;
        this.gate = gate;
    }

    public SseEmitter subscribe() {
        if (!gate.acquire()) {
            throw ApiException.capacityExceeded("事件流连接数已达上限，请稍后重试");
        }
        SseEmitter emitter = new SseEmitter(0L);
        emitter.onCompletion(() -> close(emitter));
        emitter.onTimeout(() -> close(emitter));
        emitter.onError(error -> close(emitter));
        emitters.add(emitter);
        try {
            String snapshot = snapshot();
            emitter.send(SseEmitter.event().data(snapshot));
            last = snapshot;
        } catch (Exception exception) {
            close(emitter);
        }
        return emitter;
    }

    private void close(SseEmitter emitter) {
        if (emitters.remove(emitter)) {
            gate.release();
        }
    }

    @Scheduled(fixedDelayString = "${mailbus.stream-interval-ms:15000}")
    public void tick() {
        if (emitters.isEmpty()) {
            return;
        }
        String snapshot;
        try {
            snapshot = snapshot();
        } catch (Exception exception) {
            return;
        }
        boolean changed = !snapshot.equals(last);
        for (SseEmitter emitter : emitters) {
            try {
                if (changed) {
                    emitter.send(SseEmitter.event().data(snapshot));
                } else {
                    emitter.send(SseEmitter.event().comment("heartbeat"));
                }
            } catch (Exception exception) {
                close(emitter);
                try {
                    emitter.complete();
                } catch (Exception ignored) {
                    // 已断开
                }
            }
        }
        if (changed) {
            last = snapshot;
        }
    }

    private String snapshot() throws Exception {
        Map<String, Object> payload = new LinkedHashMap<>();
        ObservabilityDtos.OverviewOut overviewOut = overview.get();
        payload.put("overview", overviewOut);
        payload.put("log", overview.log(20));
        return objectMapper.writeValueAsString(payload);
    }
}
