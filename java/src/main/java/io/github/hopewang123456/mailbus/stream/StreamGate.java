package io.github.hopewang123456.mailbus.stream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

/** 进程内长连接闸门：概览事件流与大屏事件流共享同一容量上限。 */
@Component
public class StreamGate {

    private final int capacity;
    private final AtomicInteger active = new AtomicInteger();

    public StreamGate(@Value("${mailbus.sse-max-streams:256}") int capacity) {
        this.capacity = Math.max(0, capacity);
    }

    public boolean acquire() {
        while (true) {
            int current = active.get();
            if (current >= capacity) {
                return false;
            }
            if (active.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    public void release() {
        active.updateAndGet(value -> value > 0 ? value - 1 : 0);
    }

    public boolean full() {
        return active.get() >= capacity;
    }

    public int active() {
        return active.get();
    }

    public int capacity() {
        return capacity;
    }
}
