package io.github.hopewang123456.mailbus.adapters.migration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/**
 * Reads a Python-mailbus store layout (one inbox.json per agent holding the
 * full message array — the audit's L1/L2 legacy) and yields normalized
 * MsgRecords plus a preserved raw JSON body per message.
 *
 * Normalization rules (plan §5.1 schema discipline):
 * - state wins over status (Python SoT); unknown values fall back to PENDING + warning
 * - timestamps: explicit offsets honored; offset-less strings are interpreted
 *   as Asia/Shanghai (the Python process sets TZ=Asia/Shanghai) and converted to UTC
 * - ops bookkeeping fields (api_stall_*, pushed_count, repush_after, ...) are NOT
 *   mapped into the record — they stay in the preserved raw body
 */
public class PythonStoreReader implements io.github.hopewang123456.mailbus.ports.StoreMigrator {

    private static final ZoneId PY_TZ = ZoneId.of("Asia/Shanghai");
    private static final ObjectMapper JSON = new ObjectMapper();

    private final Path pythonStoreRoot;

    public PythonStoreReader(Path pythonStoreRoot) {
        this.pythonStoreRoot = pythonStoreRoot;
    }

    @Override
    public Result readAll() {
        List<io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage> out = new ArrayList<>();
        List<String> warns = new ArrayList<>();
        Path inboxDir = pythonStoreRoot.resolve("inbox");
        if (!Files.isDirectory(inboxDir)) {
            throw new IllegalArgumentException("not a python store (no inbox/): " + pythonStoreRoot);
        }
        int agents = 0;
        try (var stream = Files.list(inboxDir)) {
            for (Path agentDir : stream.filter(Files::isDirectory).sorted().toList()) {
                Path inboxJson = agentDir.resolve("inbox.json");
                if (!Files.isRegularFile(inboxJson)) {
                    continue;
                }
                agents++;
                JsonNode root = JSON.readTree(Files.readString(inboxJson, StandardCharsets.UTF_8));
                for (Iterator<JsonNode> it = root.path("messages").elements(); it.hasNext(); ) {
                    JsonNode m = it.next();
                    if (m.path("id").asText("").isBlank()) {
                        continue; // empty / placeholder entries
                    }
                    out.add(parseOne(m, warns));
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return new Result(out, warns, agents);
    }

    private io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage parseOne(JsonNode m, List<String> warns) {
        List<String> local = new ArrayList<>();
        String id = m.path("id").asText();
        MessageState state = mapState(m, id, local);
        MsgRecord.Priority prio = mapPriority(m.path("priority").asText("normal"), id, local);
        Instant created = mapTime(m.path("created_at").asText(null), id, local);
        Instant updated = mapTime(firstNonBlank(
                m.path("updated_at").asText(null),
                m.path("acknowledged_at").asText(null)), id, local);
        if (updated == Instant.EPOCH) {
            updated = created;
        }
        String raw;
        try {
            raw = JSON.writeValueAsString(m);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return new io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage(new MsgRecord(
                id,
                m.path("to").asText(id),
                m.path("from").asText("system"),
                m.path("type").asText("notice"),
                m.path("content").asText(""),
                prio, state, created, updated), raw, local);
    }

    private static MessageState mapState(JsonNode m, String id, List<String> warns) {
        // state is the SoT; status is the legacy duplicate (audit L2)
        String raw = m.path("state").asText(m.path("status").asText("")).trim().toLowerCase(Locale.ROOT);
        return switch (raw) {
            case "", "pending" -> MessageState.PENDING;
            case "pushed" -> MessageState.PUSHED;
            case "processing" -> MessageState.PROCESSING;
            case "done" -> MessageState.DONE;
            case "acknowledged" -> MessageState.ACKNOWLEDGED;
            case "rejected" -> MessageState.REJECTED;
            case "archived" -> MessageState.ARCHIVED;
            default -> {
                warns.add(id + ": unknown state '" + raw + "' -> PENDING");
                yield MessageState.PENDING;
            }
        };
    }

    private static MsgRecord.Priority mapPriority(String raw, String id, List<String> warns) {
        return switch (raw.trim().toLowerCase(Locale.ROOT)) {
            case "urgent" -> MsgRecord.Priority.URGENT;
            case "high" -> MsgRecord.Priority.HIGH;
            case "low" -> MsgRecord.Priority.LOW;
            default -> MsgRecord.Priority.NORMAL;
        };
    }

    private static Instant mapTime(String raw, String id, List<String> warns) {
        if (raw == null || raw.isBlank()) {
            return Instant.EPOCH;
        }
        // python emits compact offsets (+0800); ISO_OFFSET_DATE_TIME wants +08:00
        String norm = raw.replaceAll("([+-]\\d{2})(\\d{2})$", "$1:$2");
        try {
            return OffsetDateTime.parse(norm, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();
        } catch (DateTimeParseException ignored) {
            // fall through to offset-less handling
        }
        try {
            return java.time.LocalDateTime.parse(norm, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                    .atZone(PY_TZ).toInstant();
        } catch (DateTimeParseException e) {
            warns.add(id + ": unparsable time '" + raw + "' -> EPOCH");
            return Instant.EPOCH;
        }
    }

    private static String firstNonBlank(String a, String b) {
        return a != null && !a.isBlank() ? a : b;
    }

    /** Adapter-side factory bean (stateless). */
    public static class Factory implements io.github.hopewang123456.mailbus.ports.StoreMigrator.Factory {
        @Override
        public io.github.hopewang123456.mailbus.ports.StoreMigrator forRoot(java.nio.file.Path pythonStoreRoot) {
            return new PythonStoreReader(pythonStoreRoot);
        }
    }
}
