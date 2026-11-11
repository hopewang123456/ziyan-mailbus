package io.github.hopewang123456.mailbus.adapters.filestore;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批2：python inbox.json 读投影 —— 状态全集/未读口径/历史格式/缓存失效。
 */
class PythonInboxStoreTest {

    @TempDir
    Path dir;

    private void writeInbox(String agent, String body) throws IOException {
        Path agentDir = dir.resolve("inbox").resolve(agent);
        Files.createDirectories(agentDir);
        Files.writeString(agentDir.resolve("inbox.json"), body);
    }

    private static String msg(String id, String state, String created) {
        return """
                {"id":"%s","to":"a","from":"system","type":"notice","content":"c-%s",
                 "priority":"normal","status":"%s","state":"%s",
                 "created_at":"%s","updated_at":"%s","pushed_count":1}
                """.formatted(id, id, state, state, created, created);
    }

    @Test
    void projectsPythonStatesAndUnreadCount() throws Exception {
        writeInbox("a", """
                {"has_unread": true, "messages": [
                  %s, %s, %s, %s, %s, %s, %s
                ]}
                """.formatted(
                msg("m1", "pending", "2026-11-11T10:00:00+0800"),
                msg("m2", "pushed", "2026-11-11T10:01:00+0800"),
                msg("m3", "done", "2026-11-11T10:02:00+0800"),
                msg("m4", "closed", "2026-11-11T10:03:00+0800"),
                msg("m5", "failed", "2026-11-11T10:04:00+0800"),
                msg("m6", "sent", "2026-11-11T10:05:00+0800"),
                msg("m7", "received", "2026-11-11T10:06:00+0800")));

        PythonInboxStore store = new PythonInboxStore(dir);
        assertEquals(List.of("a"), store.agents());
        assertEquals(7, store.messagesOf("a").size());
        // 未读 = 非终态（pending/pushed/received），closed/failed/sent 与 done 同属终态
        assertEquals(3, store.unreadCount("a"));
        assertTrue(store.hasUnread("a"));

        var first = store.messagesOf("a").get(0).record();
        assertEquals(MessageState.PENDING, first.state());
        // +0800 无冒号偏移 → UTC
        assertEquals(Instant.parse("2026-11-11T02:00:00Z"), first.createdAt());
        assertEquals(MessageState.CLOSED, store.messagesOf("a").get(3).record().state());
    }

    @Test
    void supportsLegacyListForm() throws Exception {
        writeInbox("b", "[" + msg("old1", "done", "2026-11-10T09:00:00+0800") + "]");
        PythonInboxStore store = new PythonInboxStore(dir);
        assertEquals(1, store.messagesOf("b").size());
        assertTrue(store.hasUnread("b"), "历史 list 形视为有未读（python 兼容分支）");
        assertEquals(0, store.unreadCount("b"));
    }

    @Test
    void cacheInvalidatesWhenFileChanges() throws Exception {
        writeInbox("a", "{\"messages\":[" + msg("m1", "pushed", "2026-11-11T10:00:00+0800") + "]}");
        PythonInboxStore store = new PythonInboxStore(dir);
        assertEquals(1, store.messagesOf("a").size());

        writeInbox("a", "{\"messages\":["
                + msg("m1", "pushed", "2026-11-11T10:00:00+0800") + ","
                + msg("m2", "done", "2026-11-11T10:01:00+0800") + "]}");
        // 强制 mtime 前进（同秒写入可能命中旧快照）
        Files.setLastModifiedTime(dir.resolve("inbox/a/inbox.json"),
                FileTime.fromMillis(System.currentTimeMillis() + 2000));

        assertEquals(2, store.messagesOf("a").size());
    }

    @Test
    void findByIdSpansAgentsAndCountsGroupByState() throws Exception {
        writeInbox("a", "{\"messages\":[" + msg("m1", "pushed", "2026-11-11T10:00:00+0800") + "]}");
        writeInbox("b", "{\"messages\":[" + msg("m2", "closed", "2026-11-11T10:00:00+0800") + "]}");
        PythonInboxStore store = new PythonInboxStore(dir);

        assertEquals("b", store.findById("m2").orElseThrow().agent());
        assertTrue(store.findById("nope").isEmpty());

        List<MessageRepository.AgentStateCount> counts = store.counts();
        assertEquals(2, counts.size());
        assertEquals("a", counts.get(0).agent());
        assertEquals("PUSHED", counts.get(0).state());
        assertEquals(1, counts.get(0).count());
    }

    @Test
    void unknownStateFallsBackToPendingWithWarning() throws Exception {
        writeInbox("a", "{\"messages\":[" + msg("m1", "weird", "2026-11-11T10:00:00+0800") + "]}");
        PythonInboxStore store = new PythonInboxStore(dir);
        assertEquals(MessageState.PENDING, store.messagesOf("a").get(0).record().state());
        assertEquals(1, store.unreadCount("a"));
        assertFalse(store.warnings().isEmpty());
    }

    @Test
    void missingInboxDirIsEmpty() {
        PythonInboxStore store = new PythonInboxStore(dir.resolve("nope"));
        assertTrue(store.agents().isEmpty());
        assertEquals(0, store.unreadCount("ghost"));
        assertFalse(store.hasUnread("ghost"));
    }
}
