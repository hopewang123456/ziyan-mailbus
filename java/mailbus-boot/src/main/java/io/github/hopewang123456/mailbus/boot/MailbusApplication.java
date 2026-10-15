package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.filestore.FileMessageStore;
import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.adapters.sqlite.SqliteMessageRepository;
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
    InboxService inboxService(@org.springframework.beans.factory.annotation.Qualifier("messageRepository")
                               MessageRepository messages, Clock clock) {
        return new InboxService(messages, clock);
    }
}
