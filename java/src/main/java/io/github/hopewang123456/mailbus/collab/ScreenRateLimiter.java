package io.github.hopewang123456.mailbus.collab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** 公开大屏接口的滑动窗口限流；进程内实现，后续可替换 Redis。 */
@Component
public class ScreenRateLimiter {

    private final int maxEvents;
    private final long windowMillis;
    private final Map<String, Deque<Long>> hits = new ConcurrentHashMap<>();

    public ScreenRateLimiter(
            @Value("${mailbus.screen-rate-limit:10}") int maxEvents,
            @Value("${mailbus.screen-rate-window-seconds:60}") long windowSeconds) {
        this.maxEvents = maxEvents;
        this.windowMillis = windowSeconds * 1000L;
    }

    public boolean allow(String key) {
        long now = System.currentTimeMillis();
        Deque<Long> window = hits.computeIfAbsent(key, ignored -> new ArrayDeque<>());
        synchronized (window) {
            while (!window.isEmpty() && now - window.peekFirst() >= windowMillis) {
                window.pollFirst();
            }
            if (window.size() >= maxEvents) {
                return false;
            }
            window.addLast(now);
            return true;
        }
    }
}
