package io.github.hopewang123456.mailbus.cli;

import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.DemoService;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.app.MigrationService;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import org.springframework.stereotype.Component;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import picocli.CommandLine.Parameters;

import java.util.List;
import java.util.concurrent.Callable;

/**
 * mailbus-j CLI — mirrors the Python command surface (send / inbox / ack).
 * Subcommands are Spring beans (constructor-injected InboxService), wired by
 * the picocli-spring boot starter in mailbus-boot.
 */
@Component
@Command(name = "mailbus", mixinStandardHelpOptions = true, version = "mailbus-j 0.1.0-SNAPSHOT",
        subcommands = {MailbusCommand.SendCommand.class, MailbusCommand.InboxCommand.class,
                MailbusCommand.AckCommand.class, MailbusCommand.MigrateCommand.class,
                MailbusCommand.DemoCommand.class, MailbusCommand.ArchiveCommand.class,
                MailbusCommand.TraceCommand.class, MailbusCommand.AcceptanceCommand.class, MailbusCommand.AgentAddCommand.class,
                MailbusCommand.AgentsCommand.class, MailbusCommand.PushCommand.class, MailbusCommand.TestConnectionCommand.class})
public class MailbusCommand {

    @Component
    @Command(name = "send", description = "Push a message into an agent's inbox")
    public static class SendCommand implements Callable<Integer> {

        private final InboxService inbox;

        public SendCommand(InboxService inbox) {
            this.inbox = inbox;
        }

        @Parameters(index = "0", description = "target agent id") String agent;
        @Option(names = "--msg", required = true, description = "message content") String msg;
        @Option(names = "--from", defaultValue = "system", description = "sender id") String from;

        @Override
        public Integer call() {
            MsgRecord r = inbox.send(agent, from, msg);
            System.out.printf("sent %s -> %s (%s)%n", r.id(), r.toAgent(), r.state());
            return 0;
        }
    }

    @Component
    @Command(name = "inbox", description = "List pending messages of an agent")
    public static class InboxCommand implements Callable<Integer> {

        private final InboxService inbox;

        public InboxCommand(InboxService inbox) {
            this.inbox = inbox;
        }

        @Parameters(index = "0") String agent;

        @Override
        public Integer call() {
            inbox.inbox(agent).forEach(r ->
                    System.out.printf("%s  %-9s %s  %s%n", r.createdAt(), r.state(), r.fromAgent(), r.content()));
            return 0;
        }
    }

    @Component
    @Command(name = "ack", description = "Acknowledge a message by id")
    public static class AckCommand implements Callable<Integer> {

        private final InboxService inbox;

        public AckCommand(InboxService inbox) {
            this.inbox = inbox;
        }

        @Parameters(index = "0") String messageId;

        @Override
        public Integer call() {
            return inbox.acknowledge(messageId).map(r -> {
                System.out.printf("acked %s (%s)%n", r.id(), r.state());
                return 0;
            }).orElseGet(() -> {
                System.err.println("not found: " + messageId);
                return 1;
            });
        }
    }

    @Component
    @Command(name = "migrate", description = "Migrate a Python mailbus store into the Java layout (idempotent)")
    public static class MigrateCommand implements Callable<Integer> {

        private final MigrationService migration;
        private final io.github.hopewang123456.mailbus.ports.StoreMigrator.Factory migratorFactory;
        private final MigrationService.ShardWriter shards;

        public MigrateCommand(MigrationService migration,
                              io.github.hopewang123456.mailbus.ports.StoreMigrator.Factory migratorFactory,
                              MigrationService.ShardWriter shards) {
            this.migration = migration;
            this.migratorFactory = migratorFactory;
            this.shards = shards;
        }

        @Parameters(index = "0", description = "path to the python store (contains inbox/)") String pythonStore;

        @Override
        public Integer call() {
            MigrationService.Report r = migration.migrate(java.nio.file.Path.of(pythonStore), migratorFactory.forRoot(java.nio.file.Path.of(pythonStore)), shards);
            System.out.printf("migrated: agents=%d messages=%d written=%d skipped=%d warnings=%d%n",
                    r.agents(), r.messages(), r.filesWritten(), r.filesSkipped(), r.warnings().size());
            r.warnings().stream().limit(10).forEach(w -> System.out.println("  warn: " + w));
            return 0;
        }
    }

    @Component
    @Command(name = "demo", description = "Run the zero-dependency full-lifecycle demo chain")
    public static class DemoCommand implements Callable<Integer> {

        private final DemoService demo;

        public DemoCommand(DemoService demo) {
            this.demo = demo;
        }

        @Override
        public Integer call() {
            demo.run().forEach(System.out::println);
            return 0;
        }
    }

    @Component
    @Command(name = "archive", description = "Archive settled (DONE/ACKNOWLEDGED) messages of an agent")
    public static class ArchiveCommand implements Callable<Integer> {

        private final ArchiveService archive;

        public ArchiveCommand(ArchiveService archive) {
            this.archive = archive;
        }

        @Parameters(index = "0") String agent;

        @Override
        public Integer call() {
            ArchiveService.Outcome out = archive.archiveSettled(agent);
            System.out.printf("archived %d message(s) of %s%n", out.archived(), agent);
            out.ids().forEach(id -> System.out.println("  " + id));
            return 0;
        }
    }

    @Component
    @Command(name = "trace", description = "Show a message's lifecycle trace")
    public static class TraceCommand implements Callable<Integer> {

        private final ArchiveService archive;

        public TraceCommand(ArchiveService archive) {
            this.archive = archive;
        }

        @Parameters(index = "0") String messageId;

        @Override
        public Integer call() {
            archive.trace(messageId).forEach(System.out::println);
            return 0;
        }
    }

    @Component
    @Command(name = "acceptance", description = "Run acceptance checks (storage/scheduler/patrol/serve)")
    public static class AcceptanceCommand implements Callable<Integer> {

        private final io.github.hopewang123456.mailbus.app.AcceptanceService acceptance;

        public AcceptanceCommand(io.github.hopewang123456.mailbus.app.AcceptanceService acceptance) {
            this.acceptance = acceptance;
        }

        @picocli.CommandLine.Option(names = "--api-base", description = "probe this serve base, e.g. http://127.0.0.1:9815")
        String apiBase;

        @Override
        public Integer call() {
            var items = acceptance.check(apiBase);
            items.forEach((k, v) -> System.out.printf("%-10s %-5s %s%n", k, v.status(), v.detail()));
            boolean ok = items.values().stream().allMatch(i -> "ok".equals(i.status()));
            System.out.println(ok ? "acceptance: OK" : "acceptance: WARNINGS/SKIPS present");
            return ok ? 0 : 1;
        }
    }

    @Component
    @Command(name = "agent-add", description = "Register an agent card (type preset or custom push_argv)")
    public static class AgentAddCommand implements Callable<Integer> {

        private final io.github.hopewang123456.mailbus.app.PushService.Cards cards;

        public AgentAddCommand(io.github.hopewang123456.mailbus.app.PushService.Cards cards) {
            this.cards = cards;
        }

        @Parameters(index = "0", description = "agent id") String id;
        @Parameters(index = "1", description = "framework type (claude_code|codex|cli|none)") String type;
        @Option(names = "--run-target", defaultValue = "windows", description = "windows|wsl|linux|docker") String runTarget;
        @Option(names = "--push-argv", split = ",", description = "custom argv with {MSG} slot, e.g. --push-argv=node,cli.js,-p,{MSG}") List<String> pushArgv;

        @Override
        public Integer call() {
            java.util.Map<String, Object> cfg = new java.util.HashMap<>();
            if (pushArgv != null && !pushArgv.isEmpty()) {
                cfg.put("push_argv", pushArgv);
                cfg.put("timeout_s", 300);
            }
            cards.add(id, type, runTarget, cfg);
            System.out.printf("registered %s (type=%s, run_target=%s)%n", id, type, runTarget);
            return 0;
        }
    }

    @Component
    @Command(name = "agents", description = "List registered agent cards")
    public static class AgentsCommand implements Callable<Integer> {

        private final io.github.hopewang123456.mailbus.app.PushService.Cards cards;

        public AgentsCommand(io.github.hopewang123456.mailbus.app.PushService.Cards cards) {
            this.cards = cards;
        }

        @Override
        public Integer call() {
            var all = cards.list();
            System.out.printf("%d agent(s):%n", all.size());
            all.forEach(c -> System.out.printf("  %-14s type=%-12s run=%-8s enabled=%s%n",
                    c.id(), c.type(), c.runTarget(), c.enabled()));
            return 0;
        }
    }

    @Component
    @Command(name = "push", description = "Push pending messages of an agent now (scan loop, on demand)")
    public static class PushCommand implements Callable<Integer> {

        private final io.github.hopewang123456.mailbus.app.PushService push;

        public PushCommand(io.github.hopewang123456.mailbus.app.PushService push) {
            this.push = push;
        }

        @Parameters(index = "0") String agent;

        @Override
        public Integer call() {
            var r = push.pushPending(agent);
            System.out.printf("pushed=%d failed=%d%n", r.pushed(), r.failed());
            return r.failed() == 0 ? 0 : 1;
        }
    }

    @Component
    @Command(name = "test-connection", description = "Probe an agent card: executable reachability + test push")
    public static class TestConnectionCommand implements Callable<Integer> {

        private final io.github.hopewang123456.mailbus.ports.AgentDirectory directory;

        public TestConnectionCommand(io.github.hopewang123456.mailbus.ports.AgentDirectory directory) {
            this.directory = directory;
        }

        @Parameters(index = "0", description = "agent id") String agent;

        @Override
        public Integer call() {
            var card = directory.findById(agent).orElse(null);
            if (card == null) {
                System.err.println("no agent card: " + agent);
                return 1;
            }
            // stage 1: probe
            var probe = directory.probe(card);
            System.out.println("[1/2] probe  " + (probe.ok() ? "OK  " : "FAIL") + " " + probe.error());
            if (!probe.ok()) {
                return 1;
            }
            // stage 2: test push (tiny message; role discovery = stage 3, arrives with MD cards)
            var send = directory.launch(agent, "MAILBUS-J connection test — reply briefly.");
            String digest = send.outputDigest().replace('\n', ' ');
            System.out.println("[2/2] push   " + (send.ok() ? "OK  " : "FAIL") + " "
                    + (send.ok() ? digest : send.error()));
            return send.ok() ? 0 : 1;
        }
    }
}
