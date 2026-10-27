package io.github.hopewang123456.mailbus.adapters.filestore;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * {dataDir}/tasks/{taskId}.json 文件存取 — 与 python TaskTracker 同一存储
 * （M2-S1：双栈共享任务池）。读侧宽松（未知字段原样保留），写侧原子
 * （tmp + rename，双后端并跑共享卷下不落半写文件）。
 */
public class FileTaskRepository implements TaskRepository {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Path tasksDir;

    public FileTaskRepository(Path dataDir) {
        this.tasksDir = dataDir.resolve("tasks");
    }

    @Override
    @SuppressWarnings("unchecked")
    public Optional<Map<String, Object>> find(String taskId) {
        Path p = tasksDir.resolve(taskId + ".json");
        if (!Files.isRegularFile(p)) {
            return Optional.empty();
        }
        try {
            JsonNode root = MAPPER.readTree(Files.readString(p));
            Map<String, Object> raw = MAPPER.convertValue(root, Map.class);
            // 保持插入序（LinkedHashMap），后续字段追加写回顺序稳定
            Map<String, Object> task = new LinkedHashMap<>(raw);
            return Optional.of(task);
        } catch (IOException e) {
            return Optional.empty();
        }
    }

    @Override
    public void save(String taskId, Map<String, Object> task) {
        try {
            Files.createDirectories(tasksDir);
            Path target = tasksDir.resolve(taskId + ".json");
            Path tmp = tasksDir.resolve(taskId + ".json.tmp");
            Files.writeString(tmp, MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(task));
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            throw new UncheckedIOException("cannot save task " + taskId, e);
        }
    }

    @Override
    public List<Map<String, Object>> listAll() {
        List<Map<String, Object>> out = new ArrayList<>();
        if (!Files.isDirectory(tasksDir)) {
            return out;
        }
        try (var stream = Files.list(tasksDir)) {
            stream.filter(p -> p.getFileName().toString().endsWith(".json"))
                    .sorted()
                    .forEach(p -> {
                        String id = p.getFileName().toString().replaceFirst("\\.json$", "");
                        find(id).ifPresent(out::add);
                    });
        } catch (IOException e) {
            return out;
        }
        out.sort(Comparator.comparing(t -> String.valueOf(t.getOrDefault("created_at", ""))));
        return out;
    }
}
