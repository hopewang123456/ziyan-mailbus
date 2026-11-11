package io.github.hopewang123456.mailbus.adapters.filestore;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.infra.lock.CrossProcessFileLock;
import io.github.hopewang123456.mailbus.ports.MessageInboxWriter;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/**
 * D16 批3：python {@code inbox/<agent>/inbox.json} 写适配层（唯一 SoT 的 java 写路径）。
 *
 * <p>与 python 对齐：
 * <ul>
 *   <li>锁：{@link CrossProcessFileLock}，与 python {@code file_lock} 同锁文件同字节区；</li>
 *   <li>格式：新消息 {@code id/from/to/type/priority/content/attachments/state/status/
 *       created_at/pushed_count/task_id/step_id/contract_path}，时间戳 {@code +0800}；</li>
 *   <li>ack/mark-read 语义逐行对齐 {@code ack_handler.process_ack / process_mark_read}；</li>
 *   <li>归档：{@code archive/<agent>/backlog-<stamp>.json}（python store_cleanup 格式）。</li>
 * </ul>
 *
 * <p>整文件原子替换（tmp + ATOMIC_MOVE），与 python {@code json_write} 一致。
 */
public class PythonInboxWriter implements MessageInboxWriter {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final ZoneId PY_TZ = ZoneId.of("Asia/Shanghai");
    /** python {@code now_iso()}：%Y-%m-%dT%H:%M:%S%z（偏移无冒号）。 */
    private static final DateTimeFormatter TS = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ");
    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");
    private static final Set<String> TERMINAL = Set.of(
            "done", "closed", "rejected", "failed", "archived", "sent");
    private static final Set<String> ARCHIVABLE = Set.of("done", "closed", "acknowledged");
    private static final Set<String> RESERVED = Set.of(
            "inbox.json", "ack.json", "mark.json", "forward.json");

    private final Path dataDir;
    private final Clock clock;

    public PythonInboxWriter(Path dataDir, Clock clock) {
        this.dataDir = dataDir.toAbsolutePath().normalize();
        this.clock = clock;
    }

    // ── 写路径 ─────────────────────────────────────────────────────────

    @Override
    public void append(MsgRecord record) {
        Path file = inboxFile(record.toAgent());
        CrossProcessFileLock.withLock(file, dataDir, () -> {
            ObjectNode doc = readDoc(file, record.toAgent());
            ArrayNode messages = messages(doc);
            ObjectNode m = messages.addObject();
            m.put("id", record.id());
            m.put("from", record.fromAgent());
            m.put("to", record.toAgent());
            m.put("type", record.type());
            m.put("priority", record.priority().name().toLowerCase(Locale.ROOT));
            m.put("content", record.content());
            m.putArray("attachments");
            m.put("state", "pending");
            m.put("status", "pending");
            m.put("created_at", ts(record.createdAt() == null || record.createdAt().equals(Instant.EPOCH)
                    ? Instant.now(clock) : record.createdAt()));
            m.put("pushed_count", 0);
            m.put("task_id", "");
            m.put("step_id", "");
            m.put("contract_path", "");
            doc.put("has_unread", true);
            writeDoc(file, doc);
        });
    }

    @Override
    public Optional<MsgRecord> acknowledge(String messageId) {
        Optional<Path> located = locateInbox(messageId);
        if (located.isEmpty()) {
            return Optional.empty();
        }
        Path file = located.get();
        return CrossProcessFileLock.withLock(file, dataDir,
                () -> acknowledgeLocked(file, messageId));
    }

    private Optional<MsgRecord> acknowledgeLocked(Path file, String messageId) {
        ObjectNode doc = readDoc(file, agentOf(file));
        ObjectNode m = findMessage(doc, messageId);
        if (m == null) {
            return Optional.empty();
        }
        String now = ts(Instant.now(clock));
        // python: state 为空/pending 才推进状态机（pushed/processing 等只改 status）
        String cur = lowerState(m);
        m.put("status", "acknowledged");
        m.put("acknowledged_at", now);
        if (cur.isEmpty() || cur.equals("pending")) {
            String type = m.path("type").asText("");
            m.put("received_at", now);
            if (type.equals("task") || type.equals("task_reply")) {
                m.put("state", "processing");
            } else {
                m.put("state", "done");
                m.put("done_at", now);
            }
        }
        doc.put("has_unread", recomputeHasUnread(doc));
        writeDoc(file, doc);
        return Optional.of(PythonMessageCodec.toRecord(m, new ArrayList<>()));
    }

    @Override
    public List<String> markRead(String agent, List<String> messageIds) {
        Path file = inboxFile(agent);
        if (!Files.isRegularFile(file) || messageIds == null || messageIds.isEmpty()) {
            return List.of();
        }
        return CrossProcessFileLock.withLock(file, dataDir, () -> {
            ObjectNode doc = readDoc(file, agent);
            String now = ts(Instant.now(clock));
            List<String> marked = new ArrayList<>();
            for (String id : messageIds) {
                ObjectNode m = findMessage(doc, id);
                if (m != null) {
                    m.put("status", "acknowledged");
                    m.put("acknowledged_at", now);
                    marked.add(id);
                }
            }
            if (!marked.isEmpty()) {
                doc.put("has_unread", recomputeHasUnread(doc));
                writeDoc(file, doc);
            }
            return marked;
        });
    }

    @Override
    public Optional<MsgRecord> markPushed(String messageId) {
        Optional<Path> located = locateInbox(messageId);
        if (located.isEmpty()) {
            return Optional.empty();
        }
        Path file = located.get();
        return CrossProcessFileLock.withLock(file, dataDir, () -> {
            ObjectNode doc = readDoc(file, agentOf(file));
            ObjectNode m = findMessage(doc, messageId);
            if (m == null) {
                return Optional.empty();
            }
            String now = ts(Instant.now(clock));
            m.put("state", "pushed");
            m.put("status", "pushed");
            m.put("pushed_count", m.path("pushed_count").asInt(0) + 1);
            m.put("last_pushed_at", now);
            doc.put("has_unread", recomputeHasUnread(doc));
            writeDoc(file, doc);
            return Optional.of(PythonMessageCodec.toRecord(m, new ArrayList<>()));
        });
    }

    @Override
    public List<String> archiveSettled(String agent) {
        Path file = inboxFile(agent);
        if (!Files.isRegularFile(file)) {
            return List.of();
        }
        return CrossProcessFileLock.withLock(file, dataDir, () -> {
            ObjectNode doc = readDoc(file, agent);
            ArrayNode messages = messages(doc);
            ArrayNode keep = JSON.createArrayNode();
            List<ObjectNode> archived = new ArrayList<>();
            for (JsonNode n : messages) {
                if (ARCHIVABLE.contains(lowerState(n))) {
                    ObjectNode copy = ((ObjectNode) n).deepCopy();
                    copy.put("state", "archived");
                    archived.add(copy);
                } else {
                    keep.add(n);
                }
            }
            if (archived.isEmpty()) {
                return List.of();
            }
            // 先写归档文件再裁剪 inbox（崩溃时宁可重复归档，不丢消息）
            Path dir = dataDir.resolve("archive").resolve(agent);
            String stamp = OffsetDateTime.now(clock.withZone(PY_TZ)).format(STAMP);
            ObjectNode payload = JSON.createObjectNode();
            payload.put("agent", agent);
            payload.put("archived_at", ts(Instant.now(clock)));
            payload.set("messages", JSON.createArrayNode().addAll(archived));
            writeJson(dir.resolve("backlog-" + stamp + ".json"), payload);

            doc.set("messages", keep);
            doc.put("has_unread", recomputeHasUnread(doc));
            writeDoc(file, doc);
            return archived.stream().map(m -> m.path("id").asText()).toList();
        });
    }

    @Override
    public LegacyShardReport migrateLegacyShards() {
        int agents = 0;
        int migrated = 0;
        int skipped = 0;
        List<String> warnings = new ArrayList<>();
        Path inboxRoot = dataDir.resolve("inbox");
        if (!Files.isDirectory(inboxRoot)) {
            return new LegacyShardReport(0, 0, 0, List.of());
        }
        List<Path> agentDirs;
        try (var s = Files.list(inboxRoot)) {
            agentDirs = s.filter(Files::isDirectory).sorted().toList();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        for (Path agentDir : agentDirs) {
            List<Path> shards = listShards(agentDir);
            if (shards.isEmpty()) {
                continue;
            }
            agents++;
            String agent = agentDir.getFileName().toString();
            Path file = agentDir.resolve("inbox.json");
            int[] counts = CrossProcessFileLock.withLock(file, dataDir, () -> migrateAgent(agentDir, file, shards, warnings));
            migrated += counts[0];
            skipped += counts[1];
        }
        return new LegacyShardReport(agents, migrated, skipped, List.copyOf(warnings));
    }

    private int[] migrateAgent(Path agentDir, Path file, List<Path> shards, List<String> warnings) {
        ObjectNode doc = readDoc(file, agentDir.getFileName().toString());
        ArrayNode messages = messages(doc);
        Set<String> ids = new HashSet<>();
        for (JsonNode n : messages) {
            ids.add(n.path("id").asText(""));
        }
        int migrated = 0;
        int skipped = 0;
        Path backup = agentDir.resolve("legacy-shards");
        for (Path shard : shards) {
            try {
                JsonNode node = JSON.readTree(Files.readString(shard, StandardCharsets.UTF_8));
                String id = node.path("id").asText("");
                if (id.isBlank()) {
                    warnings.add(shard.getFileName() + ": missing id, left in place");
                    skipped++;
                    continue;
                }
                if (ids.contains(id)) {
                    skipped++;
                } else {
                    messages.add(toPythonMessage(node, agentDir.getFileName().toString()));
                    ids.add(id);
                    migrated++;
                }
                Files.createDirectories(backup);
                move(shard, backup.resolve(shard.getFileName()));
            } catch (IOException e) {
                warnings.add(shard.getFileName() + ": " + e.getMessage());
                skipped++;
            }
        }
        doc.put("has_unread", recomputeHasUnread(doc));
        writeDoc(file, doc);
        return new int[]{migrated, skipped};
    }

    /** msg-v1 单文件 → python 消息 dict（D2：写侧统一 python 格式）。 */
    private ObjectNode toPythonMessage(JsonNode node, String agent) {
        ObjectNode m = JSON.createObjectNode();
        m.put("id", node.path("id").asText());
        m.put("from", node.path("from").asText("system"));
        m.put("to", node.path("to").asText(agent));
        m.put("type", node.path("type").asText("notice"));
        m.put("priority", node.path("priority").asText("normal").toLowerCase(Locale.ROOT));
        m.put("content", node.path("content").asText(""));
        m.putArray("attachments");
        String state = node.path("state").asText("pending").toLowerCase(Locale.ROOT);
        m.put("state", state);
        m.put("status", state);
        Instant created = PythonMessageCodec.mapTime(node.path("created_at").asText(null), m.path("id").asText(),
                new ArrayList<>());
        m.put("created_at", ts(created.equals(Instant.EPOCH) ? Instant.now(clock) : created));
        m.put("pushed_count", 0);
        m.put("task_id", "");
        m.put("step_id", "");
        m.put("contract_path", "");
        return m;
    }

    // ── 文件读写（原子替换）─────────────────────────────────────────────

    private Path inboxFile(String agent) {
        return dataDir.resolve("inbox").resolve(agent).resolve("inbox.json");
    }

    private ObjectNode readDoc(Path file, String agent) {
        if (Files.isRegularFile(file)) {
            try {
                JsonNode node = JSON.readTree(Files.readString(file, StandardCharsets.UTF_8));
                if (node.isArray()) { // v4.0 前纯数组格式
                    ObjectNode wrapped = JSON.createObjectNode();
                    wrapped.put("agent", agent);
                    wrapped.put("has_unread", true);
                    wrapped.set("messages", node);
                    wrapped.put("since", ts(Instant.now(clock)));
                    return wrapped;
                }
                if (node.isObject()) {
                    ObjectNode doc = (ObjectNode) node;
                    if (!doc.has("agent")) {
                        doc.put("agent", agent);
                    }
                    if (!doc.has("has_unread")) {
                        doc.put("has_unread", false);
                    }
                    if (!doc.path("messages").isArray()) {
                        doc.set("messages", JSON.createArrayNode());
                    }
                    return doc;
                }
            } catch (IOException e) {
                // 与 python json_read 一致：损坏文件按空 inbox 处理（下轮自修复）
                return emptyDoc(agent);
            }
        }
        return emptyDoc(agent);
    }

    private ObjectNode emptyDoc(String agent) {
        ObjectNode doc = JSON.createObjectNode();
        doc.put("agent", agent);
        doc.put("has_unread", false);
        doc.set("messages", JSON.createArrayNode());
        doc.put("since", ts(Instant.now(clock)));
        return doc;
    }

    private ArrayNode messages(ObjectNode doc) {
        if (!doc.path("messages").isArray()) {
            doc.set("messages", JSON.createArrayNode());
        }
        return (ArrayNode) doc.get("messages");
    }

    private void writeDoc(Path file, ObjectNode doc) {
        writeJson(file, doc);
    }

    private void writeJson(Path file, JsonNode node) {
        try {
            Files.createDirectories(file.getParent());
            Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
            Files.writeString(tmp, JSON.writerWithDefaultPrettyPrinter().writeValueAsString(node),
                    StandardCharsets.UTF_8);
            move(tmp, file);
        } catch (IOException e) {
            throw new UncheckedIOException("write failed: " + file, e);
        }
    }

    private static void move(Path from, Path to) throws IOException {
        try {
            Files.move(from, to, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(from, to, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    // ── 定位/查找 ─────────────────────────────────────────────────────

    private Optional<Path> locateInbox(String messageId) {
        Path inboxRoot = dataDir.resolve("inbox");
        if (!Files.isDirectory(inboxRoot)) {
            return Optional.empty();
        }
        List<Path> agents;
        try (var s = Files.list(inboxRoot)) {
            agents = s.filter(Files::isDirectory).sorted().toList();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        for (Path agentDir : agents) {
            Path file = agentDir.resolve("inbox.json");
            if (!Files.isRegularFile(file)) {
                continue;
            }
            try {
                JsonNode node = JSON.readTree(Files.readString(file, StandardCharsets.UTF_8));
                JsonNode msgs = node.isArray() ? node : node.path("messages");
                for (JsonNode m : msgs) {
                    if (messageId.equals(m.path("id").asText())) {
                        return Optional.of(file);
                    }
                }
            } catch (IOException e) {
                // 损坏文件跳过（python json_read 同样容错）
            }
        }
        return Optional.empty();
    }

    private static ObjectNode findMessage(ObjectNode doc, String messageId) {
        for (JsonNode n : doc.path("messages")) {
            if (messageId.equals(n.path("id").asText())) {
                return (ObjectNode) n;
            }
        }
        return null;
    }

    private static List<Path> listShards(Path agentDir) {
        try (var s = Files.list(agentDir)) {
            return s.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".json"))
                    .filter(p -> !RESERVED.contains(p.getFileName().toString()))
                    .sorted()
                    .toList();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String agentOf(Path inboxFile) {
        return inboxFile.getParent().getFileName().toString();
    }

    private static String lowerState(JsonNode m) {
        String state = m.path("state").asText("");
        if (state.isBlank()) {
            state = m.path("status").asText("");
        }
        return state.trim().toLowerCase(Locale.ROOT);
    }

    private static boolean recomputeHasUnread(ObjectNode doc) {
        for (JsonNode n : doc.path("messages")) {
            if (!TERMINAL.contains(lowerState(n))) {
                return true;
            }
        }
        return false;
    }

    private String ts(Instant instant) {
        return OffsetDateTime.ofInstant(instant, PY_TZ).format(TS);
    }

    /** 供 CLI 打印：去重后的 agent 名单（诊断用）。 */
    public Set<String> agentsWithInbox() {
        Path inboxRoot = dataDir.resolve("inbox");
        Set<String> out = new LinkedHashSet<>();
        if (!Files.isDirectory(inboxRoot)) {
            return out;
        }
        try (var s = Files.list(inboxRoot)) {
            s.filter(Files::isDirectory)
                    .filter(p -> Files.isRegularFile(p.resolve("inbox.json")))
                    .sorted()
                    .forEach(p -> out.add(p.getFileName().toString()));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return out;
    }
}
