package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.PythonInboxStore;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * D16 批2 对拍用例：java 查询面（读 python inbox.json 投影）与 python
 * {@code handlers_inbox.handle_inbox / handle_replies} 的返回形状逐字段一致。
 */
class MessageQueryServiceTest {

    @TempDir
    Path dir;

    private MessageQueryService serviceWithPythonStore() throws IOException {
        Path agentDir = dir.resolve("inbox").resolve("lingyan");
        Files.createDirectories(agentDir);
        Files.writeString(agentDir.resolve("inbox.json"), """
                {"has_unread": true, "messages": [
                  {"id":"p1","to":"lingyan","from":"lingyun","type":"task","priority":"high",
                   "content":"do it","status":"pushed","state":"pushed",
                   "created_at":"2026-11-11T10:00:00+0800","attachments":[{"name":"a.md"}],
                   "pushed_count":2},
                  {"id":"p2","to":"lingyan","from":"lingyan","type":"reply","priority":"normal",
                   "content":"done","status":"done","state":"done",
                   "created_at":"2026-11-11T09:00:00+0800","pushed_count":0},
                  {"id":"p3","to":"lingyan","from":"api","type":"notice","priority":"low",
                   "content":"fyi","status":"closed","state":"closed",
                   "created_at":"2026-11-11T08:00:00+0800","pushed_count":0}
                ]}
                """);
        return new MessageQueryService(new PythonInboxStore(dir));
    }

    @Test
    void inboxMatchesPythonHandlerShape() throws Exception {
        Map<String, Object> doc = serviceWithPythonStore().inbox("lingyan", null, 0);

        assertEquals("lingyan", doc.get("agent"));
        assertEquals(true, doc.get("has_unread"));
        assertEquals(3, doc.get("total"));
        assertEquals(1L, doc.get("unread")); // 仅 pushed 非终态
        assertEquals(false, doc.get("truncated"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) doc.get("messages");
        assertEquals(3, messages.size());
        Map<String, Object> p1 = messages.get(0);
        assertEquals(List.of("id", "from", "type", "priority", "content", "status", "state",
                "attachments", "created_at", "pushed_count"), List.copyOf(p1.keySet()));
        assertEquals("p1", p1.get("id"));
        assertEquals("lingyun", p1.get("from"));
        assertEquals("high", p1.get("priority"));
        assertEquals("pushed", p1.get("status"));
        assertEquals("pushed", p1.get("state"));
        assertEquals("2026-11-11T10:00:00+0800", p1.get("created_at"));
        assertEquals(1, ((List<?>) p1.get("attachments")).size());
        assertEquals(2, p1.get("pushed_count"));
    }

    @Test
    void inboxSupportsStatusFilterAndLimitTruncation() throws Exception {
        MessageQueryService query = serviceWithPythonStore();

        Map<String, Object> closed = query.inbox("lingyan", "closed", 0);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> closedMsgs = (List<Map<String, Object>>) closed.get("messages");
        assertEquals(1, closedMsgs.size());
        assertEquals("p3", closedMsgs.get(0).get("id"));

        Map<String, Object> limited = query.inbox("lingyan", null, 2);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> limitedMsgs = (List<Map<String, Object>>) limited.get("messages");
        assertEquals(List.of("p1", "p2"), limitedMsgs.stream().map(m -> m.get("id")).toList());
        assertEquals(true, limited.get("truncated"));
    }

    @Test
    void repliesGroupByAgentLikePython() throws Exception {
        Map<String, Object> replies = serviceWithPythonStore().replies();
        assertTrue(replies.containsKey("lingyan"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> rows = (List<Map<String, Object>>) replies.get("lingyan");
        assertEquals(1, rows.size());
        assertEquals("p2", rows.get(0).get("id"));
        assertEquals("reply", rows.get(0).get("type"));
        assertEquals("done", rows.get(0).get("state"));
    }

    @Test
    void unreadAndFindByIdFollowProjection() throws Exception {
        MessageQueryService query = serviceWithPythonStore();
        assertEquals(1, query.unread("lingyan"));
        assertEquals(0, query.unread("ghost"));
        assertTrue(query.findById("p2").isPresent());
        assertFalse(query.findById("missing").isPresent());
    }

    @Test
    void emptyAgentIsPythonEmptyShape() throws Exception {
        Map<String, Object> doc = serviceWithPythonStore().inbox("ghost", null, 0);
        assertEquals("ghost", doc.get("agent"));
        assertEquals(false, doc.get("has_unread"));
        assertEquals(0, doc.get("total"));
        assertEquals(0L, doc.get("unread"));
        assertEquals(List.of(), doc.get("messages"));
    }
}
