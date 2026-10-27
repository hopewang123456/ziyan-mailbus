package io.github.hopewang123456.mailbus.infra.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * JSON 文件读写小工具 — python {@code lib/infra/utils.py json_read/json_write}
 * 的 java 对应物。读侧失败返回 null/空（python 静默容错语义），写侧原子。
 */
public final class JsonFiles {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonFiles() {
    }

    /** 读 JSON 文件为 Map；不存在/损坏返回 null（调用方给缺省）。 */
    public static Map<String, Object> readMap(Path p) {
        JsonNode root = readTree(p);
        if (root == null || !root.isObject()) {
            return null;
        }
        return (Map<String, Object>) toPlain(root);
    }

    public static JsonNode readTree(Path p) {
        if (p == null || !Files.isRegularFile(p)) {
            return null;
        }
        try {
            return MAPPER.readTree(Files.readString(p));
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    /** 原子写（tmp + rename）。 */
    public static void write(Path p, Object value) {
        try {
            if (p.getParent() != null) {
                Files.createDirectories(p.getParent());
            }
            Path tmp = p.resolveSibling(p.getFileName() + ".tmp");
            Files.writeString(tmp, MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(value));
            Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            throw new UncheckedIOException("cannot write " + p, e);
        }
    }

    /** JsonNode → 纯 Map/List/标量（整数保 long、浮点保 double）。 */
    public static Object toPlain(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isObject()) {
            Map<String, Object> m = new LinkedHashMap<>();
            node.fields().forEachRemaining(f -> m.put(f.getKey(), toPlain(f.getValue())));
            return m;
        }
        if (node.isArray()) {
            List<Object> l = new ArrayList<>();
            node.forEach(n -> l.add(toPlain(n)));
            return l;
        }
        if (node.isIntegralNumber()) {
            return node.asLong();
        }
        if (node.isNumber()) {
            return node.asDouble();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        return node.asText();
    }
}
