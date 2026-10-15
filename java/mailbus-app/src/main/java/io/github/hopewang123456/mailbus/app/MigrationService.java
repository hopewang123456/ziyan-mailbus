package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.ports.StoreMigrator;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.nio.file.Path;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;

/**
 * Migrates a Python-mailbus store into the Java layout: Python inbox.json
 * arrays split into one-file-per-message shards + SQLite index rows.
 * Idempotent: existing shard files are left untouched; index rows upsert.
 * Report lands under &lt;dataDir&gt;/reports/migration-&lt;ts&gt;.json-style text.
 */
public class MigrationService {

    /** Read-only shard probe for migration idempotency counting. */
    public interface ShardWriter {
        boolean shardExists(io.github.hopewang123456.mailbus.domain.message.MsgRecord record);
    }

    public record Report(int agents, int messages, int filesWritten, int filesSkipped,
                         List<String> warnings) {}

    private final MessageRepository repository;
    private final java.nio.file.Path dataDir;
    private final Clock clock;

    public MigrationService(MessageRepository repository, java.nio.file.Path dataDir, Clock clock) {
        this.repository = repository;
        this.dataDir = dataDir;
        this.clock = clock;
    }

    public Report migrate(Path pythonStoreRoot, StoreMigrator migrator, ShardWriter shards) {
        StoreMigrator.Result result = migrator.readAll();
        int written = 0, skipped = 0;
        List<String> warnings = new ArrayList<>(result.warnings());
        for (StoreMigrator.RawMessage p : result.messages()) {
            if (shards.shardExists(p.record())) {
                skipped++;
            } else {
                written++;
            }
            repository.save(p.record(), p.rawJson()); // single entry: file-once + index upsert
        }
        Report report = new Report(result.agentsSeen(), result.messages().size(),
                written, skipped, warnings);
        writeReport(pythonStoreRoot, report);
        return report;
    }

    private void writeReport(Path pythonStoreRoot, Report r) {
        try {
            Path reports = dataDir.resolve("reports"); // report lands in the TARGET store
            java.nio.file.Files.createDirectories(reports);
            String ts = java.time.Instant.now(clock).toString().replace(":", "");
            StringBuilder sb = new StringBuilder("mailbus-j migration report\n");
            sb.append("python store: ").append(pythonStoreRoot).append('\n');
            sb.append("agents: ").append(r.agents()).append("  messages: ").append(r.messages()).append('\n');
            sb.append("shards written: ").append(r.filesWritten()).append("  skipped(existing): ").append(r.filesSkipped()).append('\n');
            sb.append("warnings: ").append(r.warnings().size()).append('\n');
            r.warnings().forEach(w -> sb.append("  - ").append(w).append('\n'));
            java.nio.file.Files.writeString(
                    reports.resolve("migration-" + ts + ".txt"), sb.toString());
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }
}
