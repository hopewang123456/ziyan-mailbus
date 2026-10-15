package io.github.hopewang123456.mailbus.adapters.notify;

import io.github.hopewang123456.mailbus.ports.Notifier;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;

/**
 * File digest channel (python `file` notify counterpart): appends one line
 * per notification to &lt;dataDir&gt;/reports/digest-&lt;yyyy-MM-dd&gt;.txt —
 * the human-readable daily trail. UTC dating (domain discipline).
 */
public class FileDigestNotifier implements Notifier {

    private final Path dataDir;
    private final Clock clock;

    public FileDigestNotifier(Path dataDir, Clock clock) {
        this.dataDir = dataDir;
        this.clock = clock;
    }

    @Override
    public void notify(Level level, String title, String body) {
        Instant now = Instant.now(clock);
        String day = now.toString().substring(0, 10);
        Path file = dataDir.resolve("reports").resolve("digest-" + day + ".txt");
        String line = now + " [" + level + "] " + title + " — "
                + (body == null ? "" : body.replace("\n", " ")) + System.lineSeparator();
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, line, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
