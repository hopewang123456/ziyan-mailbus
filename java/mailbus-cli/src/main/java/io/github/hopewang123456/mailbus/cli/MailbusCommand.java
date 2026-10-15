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
                MailbusCommand.TraceCommand.class, MailbusCommand.AcceptanceCommand.class})
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

        @Override
        public Integer call() {
            var items = acceptance.check();
            items.forEach((k, v) -> System.out.printf("%-10s %-5s %s%n", k, v.status(), v.detail()));
            boolean ok = items.values().stream().allMatch(i -> "ok".equals(i.status()));
            System.out.println(ok ? "acceptance: OK" : "acceptance: WARNINGS/SKIPS present");
            return ok ? 0 : 1;
        }
    }
}
