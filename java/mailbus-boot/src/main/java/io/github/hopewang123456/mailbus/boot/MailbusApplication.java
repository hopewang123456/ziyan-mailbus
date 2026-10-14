package io.github.hopewang123456.mailbus.boot;

import io.github.hopewang123456.mailbus.adapters.memory.InMemoryMessageRepository;
import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.ports.MessageRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.time.Clock;

/**
 * mailbus-j composition root — the ONLY module allowed to see every layer
 * (Python composition.py counterpart). Production storage binding swaps
 * InMemoryMessageRepository for the SQLite adapter via profile/config.
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

    @Bean
    MessageRepository messageRepository() {
        // M1 grows the SQLite-backed implementation; in-memory backs demo/tests for now.
        return new InMemoryMessageRepository();
    }

    @Bean
    InboxService inboxService(MessageRepository messages, Clock clock) {
        return new InboxService(messages, clock);
    }
}
