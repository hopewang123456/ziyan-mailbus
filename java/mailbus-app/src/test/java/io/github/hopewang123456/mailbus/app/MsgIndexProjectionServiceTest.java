package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.adapters.filestore.PythonInboxStore;
import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * D16 批2：msg_index 全量重建 —— 索引是投影缓存，重建后与 python SoT 一致，
 * 且不残留旧索引行（stale 索引可随时丢弃）。
 */
class MsgIndexProjectionServiceTest {

    @TempDir
    Path dir;

    @Test
    void rebuildReplacesIndexWithPythonSourceOfTruth() throws IOException {
        Path a = dir.resolve("inbox").resolve("lingyan");
        Files.createDirectories(a);
        Files.writeString(a.resolve("inbox.json"), """
                {"messages": [
                  {"id":"m1","to":"lingyan","from":"system","type":"notice","content":"x",
                   "state":"pushed","created_at":"2026-11-11T10:00:00+0800"},
                  {"id":"m2","to":"lingyan","from":"system","type":"notice","content":"y",
                   "state":"closed","created_at":"2026-11-11T10:01:00+0800"}
                ]}
                """);

        InMemoryMessageRepository index = new InMemoryMessageRepository();
        index.save(new MsgRecord("stale", "ghost", "system", "notice", "old",
                MsgRecord.Priority.NORMAL, MessageState.PENDING, Instant.EPOCH, Instant.EPOCH));

        PythonInboxStore source = new PythonInboxStore(dir);
        var report = new MsgIndexProjectionService(source, index).rebuild();

        assertEquals(1, report.agents());
        assertEquals(2, report.messages());
        assertEquals(List.of("m1", "m2"), index.allIds());
        assertEquals(MessageState.CLOSED, index.findById("m2").orElseThrow().state());
    }
}
