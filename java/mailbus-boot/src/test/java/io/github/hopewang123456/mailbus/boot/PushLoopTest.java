package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.frameworks.CliAgentDirectory;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteEventLog;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.PushService;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
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
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** M3 scan/push loop: agent cards + declarative argv launcher + state flip. */
class PushLoopTest {

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
    void fakeCliAgentPushesPendingToPushed() {
        var jdbc = new JdbcTemplate(ds);
        var events = new SqliteEventLog(jdbc, Clock.systemUTC());
        var repo = new FileMessageStore.FileIndexedMessages(
                new FileMessageStore(tmp), new SqliteMessageRepository(jdbc));
        var directory = new CliAgentDirectory(jdbc, Clock.systemUTC());
        var inbox = new InboxService(repo, events, Clock.systemUTC());
        var push = new PushService(repo, directory, events);
        var cards = new PushService.Cards(directory);

        // declarative argv with {MSG} slot — a harmless echo command (no shell)
        cards.add("agent-fake", "cli", "windows", Map.of(
                "push_argv", List.of(System.getProperty("os.name").toLowerCase().contains("win")
                        ? "cmd" : "echo", "/C", "echo", "pushed:{MSG}"),
                "timeout_s", 30));

        var m = inbox.send("agent-fake", "tester", "hello m3");
        var r = push.pushPending("agent-fake");

        assertEquals(1, r.pushed());
        assertEquals(0, r.failed());
        assertEquals(MessageState.PUSHED, repo.findById(m.id()).orElseThrow().state());
        assertTrue(events.eventsOf(m.id()).stream()
                .anyMatch(e -> "pushed".equals(e.kind()) && e.detail().contains("hello m3")));

        // second sweep: nothing PENDING left
        assertEquals(0, push.pushPending("agent-fake").pushed());
    }

    @Test
    void runTargetDispatchWrapsArgvCorrectly() {
        // windows/linux: untouched
        assertEquals(List.of("a", "b"),
                CliAgentDirectory.wrapForRunTarget("windows", List.of("a", "b")));
        assertEquals(List.of("a", "b"),
                CliAgentDirectory.wrapForRunTarget("linux", List.of("a", "b")));
        // wsl: wsl -e prefix
        assertEquals(List.of("wsl", "-e", "a", "b"),
                CliAgentDirectory.wrapForRunTarget("wsl", List.of("a", "b")));
        // docker: first token = container by convention; on a Windows host without
        // a native docker.exe the engine lives in WSL -> wsl -e prefix (python runtime_net topology)
        boolean wslHost = System.getProperty("os.name", "").toLowerCase().contains("win")
                && !java.nio.file.Files.isRegularFile(java.nio.file.Path.of(
                        "C:/Program Files/Docker/Docker/resources/bin/docker.exe"));
        List<String> expected = wslHost
                ? List.of("wsl", "-e", "docker", "exec", "ctr", "run", "x")
                : List.of("docker", "exec", "ctr", "run", "x");
        assertEquals(expected, CliAgentDirectory.wrapForRunTarget("docker", List.of("ctr", "run", "x")));
    }

    @Test
    void wslAgentPushesThroughWslExe() {
        // real WSL on this host runs the production line — verify the wrapper end to end
        org.junit.jupiter.api.Assumptions.assumeTrue(
                java.nio.file.Path.of("C:/Windows/System32/wsl.exe").toFile().exists(),
                "wsl not present");
        var jdbc = new JdbcTemplate(ds);
        var events = new SqliteEventLog(jdbc, Clock.systemUTC());
        var repo = new FileMessageStore.FileIndexedMessages(
                new FileMessageStore(tmp), new SqliteMessageRepository(jdbc));
        var directory = new CliAgentDirectory(jdbc, Clock.systemUTC());
        var inbox = new InboxService(repo, events, Clock.systemUTC());
        var push = new PushService(repo, directory, events);

        new PushService.Cards(directory).add("agent-wsl", "cli", "wsl", Map.of(
                "push_argv", List.of("echo", "wsl-pushed:{MSG}"), "timeout_s", 30));
        inbox.send("agent-wsl", "tester", "cross-boundary");
        var r = push.pushPending("agent-wsl");

        assertEquals(1, r.pushed(), "wsl -e echo must run via the dispatcher");
        assertTrue(events.eventsOf(
                        repo.findByAgentAndState("agent-wsl", MessageState.PUSHED).get(0).id())
                .stream().anyMatch(e -> "pushed".equals(e.kind())));
    }

    @Test
    void failedSpawnStaysPendingAndLogsEvent() {
        var jdbc = new JdbcTemplate(ds);
        var events = new SqliteEventLog(jdbc, Clock.systemUTC());
        var repo = new FileMessageStore.FileIndexedMessages(
                new FileMessageStore(tmp), new SqliteMessageRepository(jdbc));
        var directory = new CliAgentDirectory(jdbc, Clock.systemUTC());
        var inbox = new InboxService(repo, events, Clock.systemUTC());
        var push = new PushService(repo, directory, events);

        new PushService.Cards(directory).add("agent-dead", "cli", "windows", Map.of(
                "push_argv", List.of("definitely-not-a-command-xyz", "{MSG}"), "timeout_s", 5));

        var m = inbox.send("agent-dead", "tester", "will fail");
        var r = push.pushPending("agent-dead");

        assertEquals(0, r.pushed());
        assertEquals(1, r.failed());
        assertEquals(MessageState.PENDING, repo.findById(m.id()).orElseThrow().state());
        assertTrue(events.eventsOf(m.id()).stream().anyMatch(e -> "push_failed".equals(e.kind())));
    }
}
