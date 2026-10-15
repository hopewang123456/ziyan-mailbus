package io.github.hopewang123456.mailbus.adapters.filestore;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Files-as-source-of-truth store: one message = one JSON file under
 * &lt;store&gt;/inbox/&lt;agent&gt;/&lt;msg-id&gt;.json (plan §5.1).
 *
 * Writes are atomic: tmp file + ATOMIC_MOVE (falls back to non-atomic move
 * on filesystems without support — same contract as the Python writer).
 * This class owns the FILES; the Sqlite index is kept in sync by the
 * composite {@link FileIndexedMessages} — never by callers.
 */
public class FileMessageStore implements io.github.hopewang123456.mailbus.ports.MessageArchiver {

    private final Path storeRoot;

    public FileMessageStore(Path storeRoot) {
        this.storeRoot = storeRoot;
    }

    public Path root() {
        return storeRoot;
    }

    public Path write(MsgRecord r) {
        return write(r, null);
    }

    /** Target shard path (inbox/<agent>/<id>.json) — used for idempotency checks. */
    public Path shardPath(MsgRecord r) {
        return storeRoot.resolve("inbox").resolve(r.toAgent()).resolve(r.id() + ".json");
    }

    /** Shard path by coordinates (no record needed). */
    public Path shardPathById(String id, String agent) {
        return storeRoot.resolve("inbox").resolve(agent).resolve(id + ".json");
    }

    /** Write with the preserved raw source body (migration provenance). */
    public Path write(MsgRecord r, String rawJson) {
        Path dir = storeRoot.resolve("inbox").resolve(r.toAgent());
        Path target = dir.resolve(r.id() + ".json");
        try {
            Files.createDirectories(dir);
            Path tmp = dir.resolve(r.id() + ".json.tmp");
            Files.writeString(tmp, toJson(r, rawJson), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            try {
                Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
            }
            return target;
        } catch (IOException e) {
            throw new UncheckedIOException("write failed for " + r.id(), e);
        }
    }

    @Override
    public Path archive(MsgRecord r) {
        String day = r.updatedAt().toString().substring(0, 10); // UTC date, ISO-8601 prefix
        Path dir = storeRoot.resolve("archive").resolve(r.toAgent()).resolve(day);
        Path src = storeRoot.resolve("inbox").resolve(r.toAgent()).resolve(r.id() + ".json");
        try {
            Files.createDirectories(dir);
            if (Files.exists(src)) {
                Files.move(src, dir.resolve(r.id() + ".json"),
                        StandardCopyOption.REPLACE_EXISTING);
            } else {
                // message never had a file (e.g. migrated index-only) — materialize the archive copy
                Files.writeString(dir.resolve(r.id() + ".json"), toJson(r), StandardCharsets.UTF_8);
            }
            return dir.resolve(r.id() + ".json");
        } catch (IOException e) {
            throw new UncheckedIOException("archive failed for " + r.id(), e);
        }
    }

    /**
     * Composite MessageRepository: file writes + SQLite index in one save.
     * Files lead (write first), the index follows — a crash between the two
     * leaves an unindexed file, recoverable by a rescan; never a dangling index.
     */
    public static final class FileIndexedMessages implements MessageRepository {

        private final FileMessageStore files;
        private final MessageRepository index;

        public FileIndexedMessages(FileMessageStore files, MessageRepository index) {
            this.files = files;
            this.index = index;
        }

        @Override
        public void save(MsgRecord record) {
            files.write(record); // regular upsert: file reflects latest state
            index.save(record);
        }

        @Override
        public void save(MsgRecord record, String rawJson) {
            if (!Files.isRegularFile(files.shardPath(record))) {
                files.write(record, rawJson); // import: write once, with provenance
            }
            index.save(record);
        }

        @Override
        public java.util.Optional<MsgRecord> findById(String id) {
            return index.findById(id);
        }

        @Override
        public List<MsgRecord> findByAgentAndState(String agent, MessageState state) {
            return index.findByAgentAndState(agent, state);
        }

        @Override
        public List<MsgRecord> findStalePending(String agent, Instant cutoff) {
            return index.findStalePending(agent, cutoff);
        }

        @Override
        public long countUnread(String agent) {
            return index.countUnread(agent);
        }

        public List<Path> filesOf(String agent) {
            Path dir = files.storeRoot.resolve("inbox").resolve(agent);
            if (!Files.isDirectory(dir)) {
                return List.of();
            }
            List<Path> out = new ArrayList<>();
            try (var s = Files.list(dir)) {
                s.filter(p -> p.getFileName().toString().endsWith(".json"))
                        .sorted()
                        .forEach(out::add);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
            return out;
        }
    }

    /** Minimal stable JSON serialization (no Jackson dep in this layer). */
    static String toJson(MsgRecord r) {
        return toJson(r, null);
    }

    static String toJson(MsgRecord r, String rawJson) {
        StringBuilder sb = new StringBuilder(256);
        sb.append("{\n  \"schema\": \"msg-v1\",\n");
        sb.append("  \"id\": ").append(q(r.id())).append(",\n");
        sb.append("  \"to\": ").append(q(r.toAgent())).append(",\n");
        sb.append("  \"from\": ").append(q(r.fromAgent())).append(",\n");
        sb.append("  \"type\": ").append(q(r.type())).append(",\n");
        sb.append("  \"content\": ").append(q(r.content())).append(",\n");
        sb.append("  \"priority\": ").append(q(r.priority().name())).append(",\n");
        sb.append("  \"state\": ").append(q(r.state().name())).append(",\n");
        sb.append("  \"created_at\": ").append(q(r.createdAt().toString())).append(",\n");
        sb.append("  \"updated_at\": ").append(q(r.updatedAt().toString()));
        if (rawJson != null && !rawJson.isBlank()) {
            sb.append(",\n  \"raw\": ").append(rawJson); // verbatim source body (migration provenance)
        }
        sb.append("\n}\n");
        return sb.toString();
    }

    private static String q(String v) {
        return "\"" + (v == null ? "" : v.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")) + "\"";
    }
}
