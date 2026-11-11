package io.github.hopewang123456.mailbus.adapters.migration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

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
                if (!Files.isRegularFile(agentDir.resolve("inbox.json"))) {
                    continue;
                }
                agents++;
                out.addAll(readAgent(agentDir, warns));
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return new Result(out, warns, agents);
    }

    /**
     * 单 agent inbox.json → 规范化消息（D16 批2：java 读投影的公共入口，
     * 与 {@link #readAll()} 共用同一套字段/状态/时间映射规则）。
     */
    public List<io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage> readAgent(
            Path agentDir, List<String> warns) {
        List<io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage> out = new ArrayList<>();
        Path inboxJson = agentDir.resolve("inbox.json");
        if (!Files.isRegularFile(inboxJson)) {
            return out;
        }
        try {
            JsonNode root = JSON.readTree(Files.readString(inboxJson, StandardCharsets.UTF_8));
            for (Iterator<JsonNode> it = root.path("messages").elements(); it.hasNext(); ) {
                JsonNode m = it.next();
                if (m.path("id").asText("").isBlank()) {
                    continue; // empty / placeholder entries
                }
                out.add(parseOne(m, warns));
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return out;
    }

    private io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage parseOne(JsonNode m, List<String> warns) {
        List<String> local = new ArrayList<>();
        // D16 批2：字段/状态/时间映射统一走 PythonMessageCodec（与在线读投影同口径）
        MsgRecord record = io.github.hopewang123456.mailbus.adapters.filestore.PythonMessageCodec
                .toRecord(m, local);
        String raw;
        try {
            raw = JSON.writeValueAsString(m);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return new io.github.hopewang123456.mailbus.ports.StoreMigrator.RawMessage(record, raw, local);
    }


    /** Adapter-side factory bean (stateless). */
    public static class Factory implements io.github.hopewang123456.mailbus.ports.StoreMigrator.Factory {
        @Override
        public io.github.hopewang123456.mailbus.ports.StoreMigrator forRoot(java.nio.file.Path pythonStoreRoot) {
            return new PythonStoreReader(pythonStoreRoot);
        }
    }
}
