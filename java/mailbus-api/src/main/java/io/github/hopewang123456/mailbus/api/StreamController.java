package io.github.hopewang123456.mailbus.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.app.CommandInboxService;
import io.github.hopewang123456.mailbus.app.MailbusMetricsCalculator;
import io.github.hopewang123456.mailbus.app.MetricsManifestService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * SSE 流端点（PY4-A 双栈）— 差量快照流。
 *
 * <p>协议与 python {@code lib/api/sse.py} 一致：
 * <pre>
 * event: snapshot   data: {…}   —— 载荷变化时推
 * event: heartbeat  data: {…}   —— 无变化时的保活帧
 * event: done       data: {…}   —— 正常结束
 * event: error      data: {…}   —— 异常
 * </pre>
 *
 * <p>并发护栏：SSE 长连接独占线程，java 侧用**有界**线程池 + 许可信号量限制
 * 同时在流数量（{@code MAX_STREAMS}），超出直接 503——不用无界线程池。
 *
 * <p>轮询节奏沿用 transport.api.stream_* 配置语义（poll/timeout/heartbeat）。
 */
@RestController
public class StreamController {

    /** 同时在流的最大连接数（与 python 侧 MAX_ACTIVE_STREAMS 对齐）。 */
    private static final int MAX_STREAMS = 8;

    /** 流的绝对存活上限（秒）。 */
    private static final long STREAM_TIMEOUT_SEC = 300;

    /** 无变化时的保活间隔（秒）。 */
    private static final long HEARTBEAT_SEC = 15;

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final CommandInboxService inbox;
    private final MetricsManifestService manifest;
    private final MailbusMetricsCalculator calculator;

    /** 有界线程池：固定线程数 + 有界队列 + 拒绝策略（超限抛 RejectedExecutionException）。 */
    private final ExecutorService pool;
    /** 并发流许可（与 MAX_STREAMS 同值；超出立即 503）。 */
    private final Semaphore permits = new Semaphore(MAX_STREAMS);

    public StreamController(CommandInboxService inbox,
                            MetricsManifestService manifest,
                            MailbusMetricsCalculator calculator) {
        this.inbox = inbox;
        this.manifest = manifest;
        this.calculator = calculator;
        AtomicInteger seq = new AtomicInteger();
        ThreadFactory tf = r -> {
            Thread t = new Thread(r, "mailbus-sse-" + seq.incrementAndGet());
            t.setDaemon(true);
            return t;
        };
        this.pool = Executors.newFixedThreadPool(MAX_STREAMS, tf);
    }

    @GetMapping("/api/command/inbox/stream")
    public SseEmitter commandInboxStream() {
        if (!permits.tryAcquire()) {
            throw new StreamLimitException("too many concurrent streams (limit " + MAX_STREAMS + ")");
        }
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_SEC * 1000);
        emitter.onCompletion(permits::release);
        emitter.onTimeout(() -> {
            permits.release();
            emitter.complete();
        });
        emitter.onError(e -> permits.release());
        submit(emitter, () -> inbox.inbox());
        return emitter;
    }

    @GetMapping("/api/metrics/stream")
    public SseEmitter metricsStream() {
        if (!permits.tryAcquire()) {
            throw new StreamLimitException("too many concurrent streams (limit " + MAX_STREAMS + ")");
        }
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_SEC * 1000);
        emitter.onCompletion(permits::release);
        emitter.onTimeout(() -> {
            permits.release();
            emitter.complete();
        });
        emitter.onError(e -> permits.release());
        submit(emitter, this::metricsPoints);
        return emitter;
    }

    /** 指标快照载荷（与 GET /api/metrics/query?granularity=point 同形）。 */
    private Map<String, Object> metricsPoints() {
        List<Map<String, Object>> points = new ArrayList<>();
        for (Map<String, Object> m : manifest.metrics()) {
            String id = String.valueOf(m.get("id"));
            Map<String, Object> p = new LinkedHashMap<>();
            p.put("metric", id);
            if (calculator.hasSource(id)) {
                Double v = calculator.currentValue(id);
                if (v != null) {
                    p.put("value", v);
                    p.put("unit", m.getOrDefault("unit", "count"));
                } else {
                    p.put("error", "no_source_in_m1");
                }
            } else {
                p.put("error", "no_source_in_m1");
            }
            points.add(p);
        }
        return Map.of("status", "ok", "points", points);
    }

    /** 提交轮询任务：载荷变化才推 snapshot，无变化发心跳。 */
    private void submit(SseEmitter emitter, java.util.function.Supplier<Map<String, Object>> loader) {
        try {
            pool.execute(() -> {
                String lastPayload = null;
                long deadline = System.currentTimeMillis() + STREAM_TIMEOUT_SEC * 1000;
                long lastBeat = System.currentTimeMillis();
                try {
                    while (System.currentTimeMillis() < deadline) {
                        Map<String, Object> payload = loader.get();
                        String encoded = MAPPER.writeValueAsString(payload);
                        if (!encoded.equals(lastPayload)) {
                            emitter.send(SseEmitter.event().name("snapshot").data(payload, org.springframework.http.MediaType.APPLICATION_JSON));
                            lastPayload = encoded;
                            lastBeat = System.currentTimeMillis();
                        } else {
                            long now = System.currentTimeMillis();
                            if (now - lastBeat >= HEARTBEAT_SEC * 1000) {
                                emitter.send(SseEmitter.event().name("heartbeat")
                                        .data(Map.of("ts", now / 1000.0), org.springframework.http.MediaType.APPLICATION_JSON));
                                lastBeat = now;
                            }
                        }
                        Thread.sleep(1000);
                    }
                    emitter.send(SseEmitter.event().name("done")
                            .data(Map.of("status", "done"), org.springframework.http.MediaType.APPLICATION_JSON));
                    emitter.complete();
                } catch (IOException | IllegalStateException e) {
                    // 客户端断开或 emitter 已完成
                    try {
                        emitter.complete();
                    } catch (RuntimeException ignored) {
                        // already completed
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    emitter.complete();
                } catch (Exception e) {
                    try {
                        emitter.send(SseEmitter.event().name("error")
                                .data(Map.of("error", "stream_error", "message", String.valueOf(e.getMessage())),
                                        org.springframework.http.MediaType.APPLICATION_JSON));
                        emitter.complete();
                    } catch (IOException ignored) {
                        // client gone
                    }
                }
            });
        } catch (RejectedExecutionException e) {
            permits.release();
            emitter.completeWithError(e);
        }
    }

    /** 并发流超限（映射为 503）。 */
    static class StreamLimitException extends RuntimeException {
        StreamLimitException(String message) {
            super(message);
        }
    }
}
