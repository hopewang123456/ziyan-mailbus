package io.github.hopewang123456.mailbus.adapters.filestore;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批3：java 写路径落 python inbox.json —— 格式/状态机/归档/回迁。
 */
class PythonInboxWriterTest {

    private static final Instant T0 = Instant.parse("2026-11-11T02:00:00Z"); // +0800 10:00:00

    @TempDir
    Path dir;

    private PythonInboxWriter writer() {
        return new PythonInboxWriter(dir, Clock.fixed(T0, ZoneOffset.UTC));
    }

    private PythonInboxStore store() {
        return new PythonInboxStore(dir);
    }

    private static MsgRecord record(String id, String type, MessageState state) {
        return new MsgRecord(id, "a", "lingyun", type, "hello " + id,
                MsgRecord.Priority.HIGH, state, T0, T0);
    }

    private JsonNode readInbox() throws IOException {
        return new ObjectMapper().readTree(Files.readString(dir.resolve("inbox/a/inbox.json")));
    }

    @Test
    void appendWritesPythonFormatAndIsVisibleToProjection() throws IOException {
        writer().append(record("msg-20261111-00123", "task", MessageState.PENDING));

        JsonNode doc = readInbox();
        assertEquals("a", doc.path("agent").asText());
        assertTrue(doc.path("has_unread").asBoolean());
        JsonNode m = doc.path("messages").get(0);
        assertEquals("msg-20261111-00123", m.path("id").asText());
        assertEquals("lingyun", m.path("from").asText());
        assertEquals("pending", m.path("state").asText());
        assertEquals("pending", m.path("status").asText());
        assertEquals("high", m.path("priority").asText());
        assertEquals("2026-11-11T10:00:00+0800", m.path("created_at").asText());
        assertEquals(0, m.path("pushed_count").asInt());
        assertTrue(m.path("attachments").isArray());

        assertEquals(1, store().messagesOf("a").size());
        assertEquals(1, store().unreadCount("a"));
    }

    @Test
    void acknowledgeTaskGoesProcessing() {
        writer().append(record("m-task", "task", MessageState.PENDING));
        var acked = writer().acknowledge("m-task").orElseThrow();

        assertEquals(MessageState.PROCESSING, acked.state());
        assertEquals(1, store().unreadCount("a")); // acknowledged 非终态（python 口径）
        JsonNode m;
        try {
            m = readInbox().path("messages").get(0);
        } catch (IOException e) {
            throw new AssertionError(e);
        }
        assertEquals("acknowledged", m.path("status").asText());
        assertEquals("processing", m.path("state").asText());
        assertTrue(m.hasNonNull("received_at"));
    }

    @Test
    void acknowledgeNoticeCompletesDirectly() {
        writer().append(record("m-notice", "notice", MessageState.PENDING));
        var acked = writer().acknowledge("m-notice").orElseThrow();

        assertEquals(MessageState.DONE, acked.state());
        assertEquals(0, store().unreadCount("a"));
        assertFalse(store().hasUnread("a"));
    }

    @Test
    void acknowledgeMissingReturnsEmpty() {
        assertTrue(writer().acknowledge("nope").isEmpty());
    }

    @Test
    void markReadOnlyTouchesStatus() {
        writer().append(record("m1", "task", MessageState.PENDING));
        assertEquals(List.of("m1"), writer().markRead("a", List.of("m1", "nope")));

        assertEquals(MessageState.PENDING, store().messagesOf("a").get(0).record().state());
        assertEquals("acknowledged", store().messagesOf("a").get(0).raw().get("status"));
        assertEquals(1, store().unreadCount("a")); // 只改 status，state 仍 pending
    }

    @Test
    void archiveSettledWritesPythonBacklogAndKeepsPending() throws IOException {
        writer().append(record("m-done", "notice", MessageState.PENDING));
        writer().acknowledge("m-done"); // non-task → done
        writer().append(record("m-pending", "task", MessageState.PENDING));

        assertEquals(List.of("m-done"), writer().archiveSettled("a"));

        Path archiveDir = dir.resolve("archive/a");
        List<Path> backlog;
        try (var s = Files.list(archiveDir)) {
            backlog = s.filter(p -> p.getFileName().toString().startsWith("backlog-")).toList();
        }
        assertEquals(1, backlog.size());
        JsonNode payload = new ObjectMapper().readTree(Files.readString(backlog.get(0)));
        assertEquals("a", payload.path("agent").asText());
        assertTrue(payload.hasNonNull("archived_at"));
        assertEquals("archived", payload.path("messages").get(0).path("state").asText());

        assertEquals(List.of("m-pending"), store().messagesOf("a").stream()
                .map(v -> v.record().id()).toList());
        assertTrue(store().hasUnread("a"));
        assertTrue(writer().archiveSettled("a").isEmpty());
    }

    @Test
    void migrateLegacyShardsIsIdempotent() throws IOException {
        Path agentDir = dir.resolve("inbox/a");
        Files.createDirectories(agentDir);
        Files.writeString(agentDir.resolve("inbox.json"),
                "{\"agent\":\"a\",\"has_unread\":false,\"messages\":[],\"since\":\"\"}");
        Files.writeString(agentDir.resolve("msg-20261001-00001.json"), """
                {"schema":"msg-v1","id":"msg-20261001-00001","to":"a","from":"system",
                 "type":"notice","content":"legacy","priority":"NORMAL","state":"DONE",
                 "created_at":"2026-10-01T02:00:00Z","updated_at":"2026-10-01T02:00:00Z"}
                """);

        var first = writer().migrateLegacyShards();
        assertEquals(1, first.migrated());
        assertEquals(0, first.skipped());
        assertEquals(1, store().messagesOf("a").size());
        assertEquals(MessageState.DONE, store().messagesOf("a").get(0).record().state());
        assertTrue(Files.isRegularFile(agentDir.resolve("legacy-shards/msg-20261001-00001.json")));
        assertFalse(Files.exists(agentDir.resolve("msg-20261001-00001.json")));

        // 第二次：源文件已移走，不重复迁入
        var second = writer().migrateLegacyShards();
        assertEquals(0, second.migrated());
        assertEquals(1, store().messagesOf("a").size());
    }

    @Test
    void migrateSkipsDuplicateId() throws IOException {
        Path agentDir = dir.resolve("inbox/a");
        Files.createDirectories(agentDir);
        Files.writeString(agentDir.resolve("inbox.json"), """
                {"agent":"a","has_unread":false,"messages":[
                  {"id":"msg-dup","to":"a","from":"system","type":"notice","content":"x",
                   "state":"pending","created_at":"2026-11-11T10:00:00+0800"}
                ],"since":""}
                """);
        Files.writeString(agentDir.resolve("msg-dup.json"), """
                {"schema":"msg-v1","id":"msg-dup","to":"a","from":"system","type":"notice",
                 "content":"dup","priority":"NORMAL","state":"PENDING",
                 "created_at":"2026-11-11T02:00:00Z","updated_at":"2026-11-11T02:00:00Z"}
                """);

        var report = writer().migrateLegacyShards();
        assertEquals(0, report.migrated());
        assertEquals(1, report.skipped());
        assertEquals(1, store().messagesOf("a").size());
    }
}
