package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.adapters.migration.PythonStoreReader;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.MigrationService;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * End-to-end migration flow in the composition root (sees every layer):
 * python inbox.json array -> shard files + SQLite index -> archive + trace.
 */
class MigrationFlowTest {

    @TempDir
    Path tmp;

    private SingleConnectionDataSource ds;
    private FileMessageStore files;
    private io.github.hopewang123456.mailbus.ports.MessageRepository repo;

    @BeforeEach
    void setUp() throws Exception {
        ds = new SingleConnectionDataSource("jdbc:sqlite:" + tmp.resolve("metadata.db"), true);
        Flyway.configure().dataSource(ds).locations("classpath:db/migration/sqlite").load().migrate();
        files = new FileMessageStore(tmp);
        repo = new FileMessageStore.FileIndexedMessages(files, new SqliteMessageRepository(new JdbcTemplate(ds)));
    }

    @AfterEach
    void tearDown() {
        if (ds != null) ds.close();
    }

    private Path seedPythonStore() throws Exception {
        Path pyStore = tmp.resolve("py-store");
        Files.createDirectories(pyStore.resolve("inbox").resolve("agent-a"));
        Files.writeString(pyStore.resolve("inbox").resolve("agent-a").resolve("inbox.json"), """
                {"agent":"agent-a","messages":[
                  {"id":"msg-m1","to":"agent-a","from":"sys","type":"task","content":"one",
                   "priority":"normal","state":"pending","created_at":"2026-10-01T00:00:00+00:00"},
                  {"id":"msg-m2","to":"agent-a","from":"sys","type":"notice","content":"two",
                   "priority":"normal","state":"done","created_at":"2026-08-15T13:07:35+0800"}
                ]}
                """);
        return pyStore;
    }

    @Test
    void fullFlowMigrateThenArchiveThenTrace() throws Exception {
        Path pyStore = seedPythonStore();
        MigrationService svc = new MigrationService(repo, tmp, Clock.systemUTC());
        MigrationService.ShardWriter shards = r -> Files.isRegularFile(files.shardPath(r));

        MigrationService.Report first = svc.migrate(pyStore,
                new PythonStoreReader.Factory().forRoot(pyStore), shards);
        assertEquals(2, first.messages());
        assertEquals(2, first.filesWritten());
        String shardBody = Files.readString(files.shardPathById("msg-m1", "agent-a"));
        assertTrue(shardBody.contains("\"raw\":"), "raw provenance preserved: " + shardBody);
        assertEquals(java.time.Instant.parse("2026-08-15T05:07:35Z"),
                repo.findById("msg-m2").orElseThrow().createdAt(), "+0800 normalized to UTC");

        // idempotent re-run
        MigrationService.Report second = svc.migrate(pyStore,
                new PythonStoreReader.Factory().forRoot(pyStore), shards);
        assertEquals(2, second.filesSkipped());
        assertEquals(0, second.filesWritten());

        // archive settles the DONE message: file moves, index flips
        ArchiveService archive = new ArchiveService(repo, files,
                new io.github.hopewang123456.mailbus.adapters.sqlite.SqliteEventLog(
                        new JdbcTemplate(ds), Clock.systemUTC()));
        ArchiveService.Outcome out = archive.archiveSettled("agent-a");
        assertEquals(1, out.archived());
        assertEquals("ARCHIVED", repo.findById("msg-m2").orElseThrow().state().name());
        assertTrue(Files.isRegularFile(
                tmp.resolve("archive").resolve("agent-a").resolve("2026-08-15").resolve("msg-m2.json")));

        // trace speaks
        assertTrue(archive.trace("msg-m2").toString().contains("ARCHIVED"));

        // report written
        try (var s = Files.list(tmp.resolve("reports"))) {
            assertTrue(s.anyMatch(p -> p.getFileName().toString().startsWith("migration-")));
        }
    }

}
