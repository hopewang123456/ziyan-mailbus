package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.adapters.migration.PythonStoreReader;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
import io.github.hopewang123456.mailbus.app.ArchiveService;
import io.github.hopewang123456.mailbus.app.DemoService;
import io.github.hopewang123456.mailbus.app.MigrationService;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageArchiver;
import io.github.hopewang123456.mailbus.ports.StoreMigrator;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

import java.nio.file.Path;
import java.time.Clock;

/**
 * mailbus-j composition root — the ONLY module allowed to see every layer
 * (Python composition.py counterpart).
 *
 * Storage selection (plan §5): mailbus.storage = sqlite (default: Flyway
 * schema + file store) | memory (demo/tests). MySQL switch is datasource
 * config only (spring.datasource.*), same repository code.
 */
@SpringBootApplication(scanBasePackages = "io.github.hopewang123456.mailbus")
@org.springframework.scheduling.annotation.EnableScheduling
public class MailbusApplication {

    public static void main(String[] args) {
        ensureDataDir(args);
        SpringApplication.run(MailbusApplication.class, args);
    }

    /** mailbus init semantics: the data dir must exist before SQLite opens (mkdir -p). */
    private static void ensureDataDir(String[] args) {
        String dir = "./store";
        for (String a : args) {
            if (a.startsWith("--mailbus.data-dir=")) dir = a.substring("--mailbus.data-dir=".length());
        }
        try {
            java.nio.file.Files.createDirectories(java.nio.file.Path.of(dir));
        } catch (java.io.IOException e) {
            throw new IllegalStateException("cannot create data dir: " + dir, e);
        }
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC(); // domain discipline: UTC only
    }

    /** Files-as-SoT layer — always present; writes flow through the composite repo. */
    @Bean
    FileMessageStore fileMessageStore(org.springframework.core.env.Environment env) {
        return new FileMessageStore(Path.of(env.getProperty("mailbus.data-dir", "./store")));
    }

    @Bean
    @ConditionalOnProperty(name = "mailbus.storage", havingValue = "sqlite", matchIfMissing = true)
    MessageRepository sqliteIndex(org.springframework.jdbc.core.JdbcTemplate jdbc) {
        return new SqliteMessageRepository(jdbc);
    }

    @Bean
    @ConditionalOnProperty(name = "mailbus.storage", havingValue = "memory")
    MessageRepository memoryIndex() {
        return new InMemoryMessageRepository();
    }

    /** Composite: file write first, index second — a crash leaves unindexed files
     *  (recoverable by rescan), never a dangling index row. */
    @Bean
    MessageRepository messageRepository(FileMessageStore files,
                                        @org.springframework.beans.factory.annotation.Qualifier("sqliteIndex")
                                        ObjectProvider<MessageRepository> sqlite,
                                        @org.springframework.beans.factory.annotation.Qualifier("memoryIndex")
                                        ObjectProvider<MessageRepository> memory) {
        MessageRepository index = sqlite.getIfAvailable() != null
                ? sqlite.getIfAvailable()
                : memory.getIfAvailable();
        if (index == null) {
            throw new IllegalStateException("no storage index bean matched (mailbus.storage=?)");
        }
        return new FileMessageStore.FileIndexedMessages(files, index);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.AgentDirectory agentDirectory(
            org.springframework.jdbc.core.JdbcTemplate jdbc, Clock clock) {
        return new io.github.hopewang123456.mailbus.adapters.frameworks.CliAgentDirectory(jdbc, clock);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PushService pushService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.AgentDirectory directory,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new io.github.hopewang123456.mailbus.app.PushService(repo, directory, events);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PushService.Cards agentCards(
            io.github.hopewang123456.mailbus.ports.AgentDirectory directory) {
        return new io.github.hopewang123456.mailbus.app.PushService.Cards(directory);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.AgentCardImporter.Factory agentCardImporterFactory() {
        return new io.github.hopewang123456.mailbus.adapters.frameworks.TransportCardImporter.Factory();
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.MessageEventLog messageEventLog(
            org.springframework.jdbc.core.JdbcTemplate jdbc, Clock clock) {
        return new io.github.hopewang123456.mailbus.adapters.sqlite.SqliteEventLog(jdbc, clock);
    }

    @Bean
    io.github.hopewang123456.mailbus.ports.Notifier notifier(FileMessageStore files,
            org.springframework.core.env.Environment env, Clock clock) {
        String webhook = env.getProperty("mailbus.notify.webhook-url", "");
        return io.github.hopewang123456.mailbus.ports.Notifier.fanOut(
                new io.github.hopewang123456.mailbus.adapters.notify.WebhookNotifier(webhook, clock),
                new io.github.hopewang123456.mailbus.adapters.notify.FileDigestNotifier(files.root(), clock));
    }

    @Bean
    io.github.hopewang123456.mailbus.app.PatrolService patrolService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events,
            io.github.hopewang123456.mailbus.ports.Notifier notifier) {
        return new io.github.hopewang123456.mailbus.app.PatrolService(repo, events, notifier);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.StatusService statusService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo) {
        return new io.github.hopewang123456.mailbus.app.StatusService(repo);
    }

    @Bean
    io.github.hopewang123456.mailbus.app.AcceptanceService acceptanceService(
            @org.springframework.beans.factory.annotation.Qualifier("messageRepository")
            io.github.hopewang123456.mailbus.ports.MessageRepository repo,
            io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new io.github.hopewang123456.mailbus.app.AcceptanceService(repo, events);
    }

    @Bean
    StoreMigrator.Factory storeMigratorFactory() {
        return new PythonStoreReader.Factory();
    }

    @Bean
    MigrationService.ShardWriter shardWriter(FileMessageStore files) {
        return record -> java.nio.file.Files.isRegularFile(files.shardPath(record));
    }

    @Bean
    MigrationService migrationService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                                      MessageRepository repo, FileMessageStore files, Clock clock) {
        return new MigrationService(repo, files.root(), clock);
    }

    @Bean
    ArchiveService archiveService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                                  MessageRepository repo, FileMessageStore files,
                                  io.github.hopewang123456.mailbus.ports.MessageEventLog events) {
        return new ArchiveService(repo, files, events);
    }

    @Bean
    DemoService demoService(InboxService inbox, ArchiveService archive) {
        return new DemoService(inbox, archive);
    }

    @Bean
    InboxService inboxService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                               MessageRepository messages,
                               io.github.hopewang123456.mailbus.ports.MessageEventLog events,
                               Clock clock) {
        return new InboxService(messages, events, clock);
    }
}
