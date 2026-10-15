package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteEventLog;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.InboxService;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;

import java.nio.file.Path;
import java.time.Clock;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Typed event stream: every send/ack/archive transition lands in msg_events. */
class EventStreamTest {

    @TempDir
    Path tmp;

    private SingleConnectionDataSource ds;

    @BeforeEach
    void setUp() {
        ds = new SingleConnectionDataSource("jdbc:sqlite:" + tmp.resolve("metadata.db"), true);
        Flyway.configure().dataSource(ds).locations("classpath:db/migration/sqlite").load().migrate();
    }

    @AfterEach
    void tearDown() {
        if (ds != null) ds.close();
    }

    @Test
    void sendAckArchiveEmitsOrderedEvents() {
        var jdbc = new JdbcTemplate(ds);
        var events = new SqliteEventLog(jdbc, Clock.systemUTC());
        var repo = new FileMessageStore.FileIndexedMessages(
                new FileMessageStore(tmp), new SqliteMessageRepository(jdbc));
        var inbox = new InboxService(repo, events, Clock.systemUTC());
        var archive = new ArchiveService(repo, new FileMessageStore(tmp), events);

        var m = inbox.send("agent-ev", "tester", "event stream probe");
        inbox.acknowledge(m.id());
        archive.archiveSettled("agent-ev");

        List<String> kinds = events.eventsOf(m.id()).stream()
                .map(e -> e.kind() + ":" + e.stateFrom() + "->" + e.stateTo()).toList();
        assertEquals(List.of(
                "created:null->PENDING",
                "state:PENDING->PROCESSING",
                "state:PROCESSING->DONE",
                "archived:DONE->ARCHIVED"), kinds);

        // trace renders the stream
        List<String> trace = archive.trace(m.id());
        assertTrue(trace.stream().anyMatch(l -> l.startsWith("events:")));
        assertTrue(trace.stream().anyMatch(l -> l.contains("archived") && l.contains("DONE -> ARCHIVED")));
    }

    @Test
    void heartbeatRoundTrips() {
        var events = new SqliteEventLog(new JdbcTemplate(ds), Clock.systemUTC());
        events.heartbeat("patrol", true, "");
        var hb = events.heartbeatOf("patrol");
        assertEquals("patrol", hb.job());
        assertTrue(hb.ok());
        events.heartbeat("patrol", false, "boom");
        assertEquals("boom", events.heartbeatOf("patrol").error());
    }
}
