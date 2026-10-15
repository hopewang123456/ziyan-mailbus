package io.github.hopewang123456.mailbus.adapters.migration;

import io.github.hopewang123456.mailbus.ports.StoreMigrator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PythonStoreReaderTest {

    @TempDir
    Path tmp;

    private void writeInbox(String agent, String json) throws Exception {
        Path dir = tmp.resolve("inbox").resolve(agent);
        Files.createDirectories(dir);
        Files.writeString(dir.resolve("inbox.json"), json);
    }

    @Test
    void mapsStatesPrioritiesAndMixedTimezones() throws Exception {
        // real-shape sample: state/status duplicates, +00:00 and +0800 offsets,
        // offset-less (CST) timestamps, ops bookkeeping fields, unknown state
        writeInbox("agent-a", """
                {
                  "agent": "agent-a",
                  "messages": [
                    {
                      "id": "msg-p1", "to": "agent-a", "from": "lingzun",
                      "type": "task", "content": "旧格式消息",
                      "priority": "urgent", "status": "pending", "state": "pending",
                      "pushed_count": 3, "api_stall_count": 2, "api_stall_reason": "x",
                      "created_at": "2026-10-05T15:07:23.558507+00:00",
                      "acknowledged_at": null
                    },
                    {
                      "id": "msg-p2", "to": "agent-a", "from": "lingjian",
                      "type": "notice", "content": "offset +0800",
                      "priority": "normal", "status": "done", "state": "done",
                      "created_at": "2026-08-15T13:07:35+0800"
                    },
                    {
                      "id": "msg-p3", "to": "agent-a", "from": "lingyan",
                      "type": "notice", "content": "offset-less CST",
                      "priority": "weird", "status": "x", "state": "processing",
                      "created_at": "2026-10-01T09:00:00"
                    }
                  ]
                }
                """);

        StoreMigrator.Result r = new PythonStoreReader(tmp).readAll();

        assertEquals(1, r.agentsSeen());
        assertEquals(3, r.messages().size());

        var m1 = r.messages().get(0);
        assertEquals("PENDING", m1.record().state().name());
        assertEquals("URGENT", m1.record().priority().name());
        assertEquals(Instant.parse("2026-10-05T15:07:23.558507Z"), m1.record().createdAt());
        // ops bookkeeping preserved only in the raw body
        assertTrue(m1.rawJson().contains("api_stall_reason"));

        var m2 = r.messages().get(1);
        assertEquals("DONE", m2.record().state().name());
        assertEquals(Instant.parse("2026-08-15T05:07:35Z"), m2.record().createdAt()); // +0800 -> UTC

        var m3 = r.messages().get(2);
        assertEquals("PROCESSING", m3.record().state().name()); // state wins over status
        assertEquals("NORMAL", m3.record().priority().name());  // unknown priority -> NORMAL
        assertEquals(Instant.parse("2026-10-01T01:00:00Z"), m3.record().createdAt()); // CST -> UTC
        // unknown priority is silent (spec'd); warnings reserved for state/time anomalies
        assertTrue(r.warnings().isEmpty());
    }

    @Test
    void skipsBlankIdsAndEmptyAgents() throws Exception {
        writeInbox("agent-b", "{\"agent\":\"agent-b\",\"messages\":[{\"id\":\"\",\"to\":\"agent-b\"}]}");
        StoreMigrator.Result r = new PythonStoreReader(tmp).readAll();
        assertEquals(1, r.agentsSeen());
        assertTrue(r.messages().isEmpty());
    }
}
