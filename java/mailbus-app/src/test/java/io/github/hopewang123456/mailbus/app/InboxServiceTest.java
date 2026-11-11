package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.PythonInboxStore;
import io.github.hopewang123456.mailbus.adapters.filestore.PythonInboxWriter;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批3：InboxService 写路径经 pyinbox.json（python 格式），读侧立即可见。
 */
class InboxServiceTest {

    @TempDir
    Path dir;

    private static final io.github.hopewang123456.mailbus.ports.MessageEventLog NO_EVENTS =
            new io.github.hopewang123456.mailbus.ports.MessageEventLog() {
                @Override
                public void append(String msgId, String agent, String kind,
                                   String stateFrom, String stateTo, String detail) { }

                @Override
                public List<Event> eventsOf(String msgId) {
                    return List.of();
                }

                @Override
                public List<Event> latest(int limit) {
                    return List.of();
                }

                @Override
                public void heartbeat(String job, boolean ok, String error) { }

                @Override
                public Heartbeat heartbeatOf(String job) {
                    return null;
                }
            };

    /** 每次取时间前进 1ms —— 避免同毫秒 msg id 撞号（python id 也是毫秒序）。 */
    private static Clock tickingClock() {
        Instant base = Instant.parse("2026-11-11T02:00:00Z");
        java.util.concurrent.atomic.AtomicInteger tick = new java.util.concurrent.atomic.AtomicInteger();
        return new Clock() {
            @Override
            public java.time.ZoneId getZone() {
                return ZoneOffset.UTC;
            }

            @Override
            public Clock withZone(java.time.ZoneId zone) {
                return this;
            }

            @Override
            public Instant instant() {
                return base.plusMillis(tick.incrementAndGet());
            }
        };
    }

    private InboxService service() {
        Clock clock = tickingClock();
        PythonInboxStore store = new PythonInboxStore(dir);
        return new InboxService(new PythonInboxWriter(dir, clock), store, NO_EVENTS, clock);
    }

    @Test
    void sendWritesPythonIdAndPendingState() {
        var sent = service().send("a", "lingyun", "hi");

        assertTrue(sent.id().matches("msg-\\d{8}-\\d{5}"), "python id 格式: " + sent.id());
        assertEquals(1, service().unreadCount("a"));
        var m = new PythonInboxStore(dir).messagesOf("a").get(0).record();
        assertEquals(MessageState.PENDING, m.state());
        assertEquals("pending", new PythonInboxStore(dir).messagesOf("a").get(0).raw().get("status"));
    }

    @Test
    void acknowledgeCompletesNoticeAndKeepsTaskInProcessing() {
        InboxService svc = service();
        var notice = svc.send("a", "lingyun", "notice");
        var task = svc.send("b", "lingyun", "task", "task");

        assertEquals(MessageState.DONE, svc.acknowledge(notice.id()).orElseThrow().state());
        assertEquals(MessageState.PROCESSING, svc.acknowledge(task.id()).orElseThrow().state());
        assertEquals(0, svc.unreadCount("a"));
        assertEquals(1, svc.unreadCount("b"));
    }

    @Test
    void markReadOnlyAcknowledgesStatus() {
        InboxService svc = service();
        var sent = svc.send("a", "lingyun", "hi");

        assertEquals(List.of(sent.id()), svc.markRead("a", List.of(sent.id(), "missing")));
        assertEquals(MessageState.PENDING,
                new PythonInboxStore(dir).messagesOf("a").get(0).record().state());
        assertEquals(1, svc.unreadCount("a"));
    }

    @Test
    void inboxListsPendingProjection() {
        InboxService svc = service();
        var sent = svc.send("a", "lingyun", "hi");
        assertEquals(1, svc.inbox("a").size());
        svc.acknowledge(sent.id());
        assertTrue(svc.inbox("a").isEmpty());
    }
}
