package io.github.hopewang123456.mailbus.adapters.sqlite;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Real-SQLite test: runs the actual Flyway migrations (V1+V2) against a temp
 * database and exercises the composite file+index repository end to end.
 */
class SqliteMessageRepositoryTest {

    @TempDir
    Path tmp;

    private MessageRepository repo;
    private FileMessageStore files;
    private SingleConnectionDataSource ds;

    @BeforeEach
    void setUp() {
        ds = new SingleConnectionDataSource(
                "jdbc:sqlite:" + tmp.resolve("metadata.db"), true);
        Flyway.configure().dataSource(ds).locations("classpath:db/migration/sqlite").load().migrate();
        files = new FileMessageStore(tmp);
        repo = new FileMessageStore.FileIndexedMessages(files, new SqliteMessageRepository(new JdbcTemplate(ds)));
    }

    @org.junit.jupiter.api.AfterEach
    void tearDown() {
        if (ds != null) {
            ds.close();  // release metadata.db so @TempDir cleanup succeeds on Windows
        }
    }

    private MsgRecord msg(String id, String to, MessageState state, String content) {
        Instant now = Instant.parse("2026-10-15T08:00:00Z");
        return new MsgRecord(id, to, "tester", "notice", content,
                MsgRecord.Priority.NORMAL, state, now, now);
    }

    @Test
    void saveThenQueryRoundTripsThroughIndexAndFile() throws java.io.IOException {
        repo.save(msg("msg-a1", "agent-x", MessageState.PENDING, "hello sqlite"));

        assertEquals(1, repo.findByAgentAndState("agent-x", MessageState.PENDING).size());
        assertEquals("hello sqlite", repo.findById("msg-a1").orElseThrow().content());
        assertEquals(1, repo.countUnread("agent-x"));

        // files-as-SoT: the file exists, atomic-write leftover tmp is gone
        Path file = tmp.resolve("inbox").resolve("agent-x").resolve("msg-a1.json");
        assertTrue(Files.isRegularFile(file), "message file must exist: " + file);
        assertFalse(Files.exists(file.resolveSibling("msg-a1.json.tmp")), "tmp must be renamed away");
        assertTrue(Files.readString(file).contains("\"schema\": \"msg-v1\""));
    }

    @Test
    void stateTransitionUpsertsTheSameRow() {
        repo.save(msg("msg-b2", "agent-y", MessageState.PENDING, "first"));
        repo.save(msg("msg-b2", "agent-y", MessageState.PROCESSING, "first"));

        assertEquals(0, repo.findByAgentAndState("agent-y", MessageState.PENDING).size());
        assertEquals(1, repo.findByAgentAndState("agent-y", MessageState.PROCESSING).size());
        assertEquals(1, repo.countUnread("agent-y"));
    }

    @Test
    void stalePendingSelectsOnlyOldOnes() {
        Instant old = Instant.parse("2026-10-01T00:00:00Z");
        Instant now = Instant.parse("2026-10-15T08:00:00Z");
        repo.save(new MsgRecord("msg-old", "agent-z", "t", "notice", "old",
                MsgRecord.Priority.NORMAL, MessageState.PENDING, old, old));
        repo.save(new MsgRecord("msg-new", "agent-z", "t", "notice", "new",
                MsgRecord.Priority.NORMAL, MessageState.PENDING, now, now));

        List<MsgRecord> stale = repo.findStalePending("agent-z", Instant.parse("2026-10-10T00:00:00Z"));
        assertEquals(1, stale.size());
        assertEquals("msg-old", stale.get(0).id());
    }

    @Test
    void terminalStatesDropOutOfUnread() {
        repo.save(msg("msg-c3", "agent-w", MessageState.DONE, "done"));
        repo.save(msg("msg-c4", "agent-w", MessageState.ARCHIVED, "archived"));
        assertEquals(0, repo.countUnread("agent-w"));
    }
}
