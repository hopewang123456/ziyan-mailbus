package io.github.hopewang123456.mailbus.adapters.filestore;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageProjection;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;

/**
 * D16 批2：python {@code inbox/<agent>/inbox.json} 的只读投影（唯一消息 SoT）。
 *
 * <p>一条 agent 一个文件、文件内 message 数组；本类只读不写（写路径批3）。
 * 读缓存按 (mtime, size) 失效，对应 python {@code json_read} 的 5s TTL 思路，
 * 但更精确——双栈共享卷下以文件状态为准。
 *
 * <p>python 口径对齐：
 * <ul>
 *   <li>兼容历史 list 形 inbox（v4.0 前格式）；</li>
 *   <li>未读 = 非终态消息数（{@code _count_unread}）；</li>
 *   <li>状态映射与迁移共用 {@link PythonMessageCodec}。</li>
 * </ul>
 */
public final class PythonInboxStore implements MessageProjection {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final TypeReference<LinkedHashMap<String, Object>> MAP_TYPE = new TypeReference<>() { };

    /** 文件快照缓存键：(mtimeMillis, size)；容量按 agent 数，无上限问题。 */
    private record Snapshot(long mtime, long size, boolean hasUnread, List<MessageView> views) { }

    private final Path dataDir;
    private final Path inboxDir;
    private final Map<String, Snapshot> cache = new ConcurrentHashMap<>();
    private final List<String> warnings = Collections.synchronizedList(new ArrayList<>());

    public PythonInboxStore(Path dataDir) {
        this.dataDir = dataDir.toAbsolutePath().normalize();
        this.inboxDir = this.dataDir.resolve("inbox");
    }

    public Path dataDir() {
        return dataDir;
    }

    /** 读取期告警（未知状态/坏时间戳），供 reconcile 报告用。 */
    public List<String> warnings() {
        return List.copyOf(warnings);
    }

    /** 失效全部缓存（写入后/对拍前调用）。 */
    public void invalidate() {
        cache.clear();
    }

    @Override
    public List<String> agents() {
        if (!Files.isDirectory(inboxDir)) {
            return List.of();
        }
        try (var stream = Files.list(inboxDir)) {
            return stream.filter(Files::isDirectory)
                    .filter(p -> Files.isRegularFile(p.resolve("inbox.json")))
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
        } catch (IOException e) {
            throw new UncheckedIOException("cannot list " + inboxDir, e);
        }
    }

    @Override
    public List<MessageView> messagesOf(String agent) {
        return snapshot(agent).views();
    }

    @Override
    public boolean hasUnread(String agent) {
        return snapshot(agent).hasUnread();
    }

    @Override
    public long unreadCount(String agent) {
        return snapshot(agent).views().stream()
                .filter(v -> !v.record().state().isTerminal())
                .count();
    }

    @Override
    public Optional<MessageView> findById(String id) {
        if (id == null || id.isBlank()) {
            return Optional.empty();
        }
        for (String agent : agents()) {
            for (MessageView v : messagesOf(agent)) {
                if (id.equals(v.record().id())) {
                    return Optional.of(v);
                }
            }
        }
        return Optional.empty();
    }

    @Override
    public List<MessageRepository.AgentStateCount> counts() {
        Map<String, Long> merged = new TreeMap<>();
        for (String agent : agents()) {
            for (MessageView v : messagesOf(agent)) {
                merged.merge(agent + "\u0000" + v.record().state().name(), 1L, Long::sum);
            }
        }
        List<MessageRepository.AgentStateCount> out = new ArrayList<>();
        merged.forEach((key, n) -> {
            int sep = key.indexOf('\u0000');
            out.add(new MessageRepository.AgentStateCount(key.substring(0, sep), key.substring(sep + 1), n));
        });
        return out;
    }

    // ── 文件读取（mtime/size 失效）─────────────────────────────────────

    private Snapshot snapshot(String agent) {
        Path file = inboxDir.resolve(agent).resolve("inbox.json");
        long mtime;
        long size;
        try {
            mtime = Files.getLastModifiedTime(file).toMillis();
            size = Files.size(file);
        } catch (IOException e) {
            cache.remove(agent);
            return new Snapshot(0, 0, false, List.of());
        }
        Snapshot cached = cache.get(agent);
        if (cached != null && cached.mtime() == mtime && cached.size() == size) {
            return cached;
        }
        Snapshot fresh = parse(agent, file);
        cache.put(agent, fresh);
        return fresh;
    }

    private Snapshot parse(String agent, Path file) {
        long mtime;
        long size;
        try {
            mtime = Files.getLastModifiedTime(file).toMillis();
            size = Files.size(file);
        } catch (IOException e) {
            return new Snapshot(0, 0, false, List.of());
        }
        JsonNode root;
        try {
            root = JSON.readTree(Files.readString(file, StandardCharsets.UTF_8));
        } catch (IOException e) {
            warnings.add(agent + ": unreadable inbox.json (" + e.getMessage() + ")");
            return new Snapshot(mtime, size, false, List.of());
        }
        boolean legacyList = root.isArray();
        JsonNode messages = legacyList ? root : root.path("messages");
        boolean hasUnread = legacyList || root.path("has_unread").asBoolean(false);
        List<MessageView> views = new ArrayList<>();
        if (messages.isArray()) {
            for (JsonNode m : messages) {
                if (m.path("id").asText("").isBlank()) {
                    continue;
                }
                List<String> local = new ArrayList<>();
                MsgRecord record = PythonMessageCodec.toRecord(m, local);
                if (!local.isEmpty()) {
                    local.forEach(w -> warnings.add(agent + "/" + w));
                }
                Map<String, Object> raw = JSON.convertValue(m, MAP_TYPE);
                views.add(new MessageView(agent, record, raw));
            }
        }
        return new Snapshot(mtime, size, hasUnread, List.copyOf(views));
    }

    // ── 读侧便捷方法（强类型查询，供 app/boot 复用）─────────────────────

    /** 全部 agent 的消息（按 agent、文件内顺序）。 */
    public List<MessageView> allMessages() {
        List<MessageView> out = new ArrayList<>();
        for (String agent : agents()) {
            out.addAll(messagesOf(agent));
        }
        return out;
    }

    /** 单 agent 强类型记录（文件内顺序）。 */
    public List<MsgRecord> recordsOf(String agent) {
        return messagesOf(agent).stream().map(MessageView::record).toList();
    }
}
