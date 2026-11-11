package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.PythonInboxStore;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批4：/api/trace、/api/events 转正 —— SoT 快照 + msg_events 事件流。
 */
class MessageTraceServiceTest {

    @TempDir
    Path dir;

    /** 最小事件日志（append-only 语义与 SqliteEventLog 一致）。 */
    private static final class FakeEvents implements MessageEventLog {
        private final List<Event> rows = new ArrayList<>();

        @Override
        public void append(String msgId, String agent, String kind,
                           String stateFrom, String stateTo, String detail) {
            rows.add(new Event(rows.size() + 1L, msgId, agent, kind, stateFrom, stateTo,
                    detail, "2026-11-11T10:00:00Z"));
        }

        @Override
        public List<Event> eventsOf(String msgId) {
            return rows.stream().filter(e -> e.msgId().equals(msgId)).toList();
        }

        @Override
        public List<Event> latest(int limit) {
            List<Event> tail = rows.subList(Math.max(0, rows.size() - limit), rows.size());
            return List.copyOf(tail);
        }

        @Override
        public void heartbeat(String job, boolean ok, String error) { }

        @Override
        public Heartbeat heartbeatOf(String job) {
            return null;
        }
    }

    private void writeInbox() throws IOException {
        Path agent = dir.resolve("inbox").resolve("a");
        Files.createDirectories(agent);
        Files.writeString(agent.resolve("inbox.json"), """
                {"has_unread": true, "messages": [
                  {"id":"m1","to":"a","from":"lingyun","type":"task","priority":"high",
                   "content":"do it","state":"processing","status":"acknowledged",
                   "created_at":"2026-11-11T10:00:00+0800"}
                ]}
                """);
    }

    @Test
    void traceCombinesSoTSnapshotWithEventStream() throws IOException {
        writeInbox();
        FakeEvents events = new FakeEvents();
        events.append("m1", "a", "created", null, "PENDING", "send");
        events.append("m1", "a", "state", "PENDING", "PROCESSING", "ack");

        Map<String, Object> body = new MessageTraceService(new PythonInboxStore(dir), events)
                .trace("m1").orElseThrow();

        assertEquals("ok", body.get("status"));
        assertEquals(true, body.get("found"));
        @SuppressWarnings("unchecked")
        Map<String, Object> message = (Map<String, Object>) body.get("message");
        assertEquals("processing", message.get("state"));
        assertEquals("lingyun", message.get("from"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> rows = (List<Map<String, Object>>) body.get("events");
        assertEquals(2, rows.size());
        assertEquals("state", rows.get(1).get("kind"));
        assertEquals("PROCESSING", rows.get(1).get("state_to"));
    }

    @Test
    void traceStillReturnsEventsForArchivedMessage() {
        FakeEvents events = new FakeEvents();
        events.append("gone", "a", "archived", "DONE", "ARCHIVED", "archive");

        Map<String, Object> body = new MessageTraceService(new PythonInboxStore(dir), events)
                .trace("gone").orElseThrow();

        assertEquals(false, body.get("found"));
        assertEquals(null, body.get("message"));
        assertEquals(1, ((List<?>) body.get("events")).size());
    }

    @Test
    void traceIsEmptyWhenNeitherMessageNorEventsExist() {
        assertTrue(new MessageTraceService(new PythonInboxStore(dir), new FakeEvents())
                .trace("nope").isEmpty());
    }

    @Test
    void recentEventsClampsLimit() {
        FakeEvents events = new FakeEvents();
        for (int i = 0; i < 7; i++) {
            events.append("m" + i, "a", "state", "PENDING", "PUSHED", "push");
        }
        MessageTraceService service = new MessageTraceService(new PythonInboxStore(dir), events);

        assertEquals(3, ((List<?>) service.recentEvents(3).get("events")).size());
        assertEquals(1, ((List<?>) service.recentEvents(0).get("events")).size()); // clamp 下限 1
        assertEquals(7, ((List<?>) service.recentEvents(999).get("events")).size()); // 不超过总量
        assertFalse(((List<?>) service.recentEvents(1).get("events")).isEmpty());
    }
}
