package io.github.hopewang123456.mailbus.dispatch;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.TokenResolver;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.config.AppProperties;
import io.github.hopewang123456.mailbus.messaging.MessageDtos;
import io.github.hopewang123456.mailbus.messaging.MessagingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/** file_bus 入站：扫描 inbound/*.json，令牌换 Actor 后走同一发送用例。 */
@Component
public class FileBusIngress {

    private static final Logger log = LoggerFactory.getLogger(FileBusIngress.class);

    private final MessagingService messages;
    private final TokenResolver tokens;
    private final ObjectMapper objectMapper;
    private final Path inbound;
    private final Path processed;
    private final Path rejected;

    public FileBusIngress(MessagingService messages, TokenResolver tokens,
                          ObjectMapper objectMapper, AppProperties properties) {
        this.messages = messages;
        this.tokens = tokens;
        this.objectMapper = objectMapper;
        Path base = properties.fileBusDir();
        this.inbound = base.resolve("inbound");
        this.processed = base.resolve("processed");
        this.rejected = base.resolve("rejected");
    }

    public record PollResult(int accepted, int rejectedCount) {
    }

    public PollResult pollOnce() {
        int accepted = 0;
        int rejectedCount = 0;
        List<Path> files;
        try {
            Files.createDirectories(inbound);
            try (Stream<Path> stream = Files.list(inbound)) {
                files = stream.filter(path -> path.getFileName().toString().endsWith(".json"))
                        .sorted().toList();
            }
        } catch (Exception exception) {
            log.warn("file_bus 入站目录不可读", exception);
            return new PollResult(0, 0);
        }
        for (Path path : files) {
            String name = path.getFileName().toString();
            Map<String, Object> payload;
            try {
                JsonNode node = objectMapper.readTree(path.toFile());
                if (node == null || !node.isObject()) {
                    move(name, rejected, "invalid_payload");
                    rejectedCount++;
                    continue;
                }
                payload = objectMapper.convertValue(node,
                        new TypeReference<Map<String, Object>>() {
                        });
            } catch (Exception exception) {
                move(name, rejected, "invalid_json");
                rejectedCount++;
                continue;
            }
            try {
                Actor actor = tokens.resolve(text(payload.get("token")));
                if (actor == null) {
                    throw ApiException.unauthorized("登录凭证无效或已过期");
                }
                String channel = text(payload.get("channel"));
                messages.send(actor, new MessageDtos.MessageIn(
                        text(payload.get("body")),
                        optional(payload.get("recipient_id")),
                        text(payload.get("kind")).isEmpty() ? "note" : text(payload.get("kind")),
                        channel.isEmpty() ? "file_bus" : channel),
                        channel.isEmpty() ? "file_bus" : channel);
            } catch (ApiException exception) {
                move(name, rejected, exception.code());
                rejectedCount++;
                continue;
            }
            move(name, processed, null);
            accepted++;
        }
        return new PollResult(accepted, rejectedCount);
    }

    private void move(String name, Path folder, String suffix) {
        if (!name.equals(name.strip()) || name.contains("/") || name.contains("\\")) {
            return;
        }
        try {
            Files.createDirectories(folder);
            int dot = name.lastIndexOf('.');
            String stem = dot < 0 ? name : name.substring(0, dot);
            String extension = dot < 0 ? "" : name.substring(dot);
            String base = suffix == null ? stem : stem + "." + suffix;
            Path target = folder.resolve(base + extension);
            int index = 1;
            while (Files.exists(target)) {
                target = folder.resolve(base + "-" + index + extension);
                index++;
            }
            Path source = inbound.resolve(name);
            if (Files.exists(source)) {
                Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (Exception exception) {
            log.warn("file_bus 入站文件移动失败：{}", name, exception);
        }
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private String optional(Object value) {
        String text = text(value).strip();
        return text.isEmpty() ? null : text;
    }
}
