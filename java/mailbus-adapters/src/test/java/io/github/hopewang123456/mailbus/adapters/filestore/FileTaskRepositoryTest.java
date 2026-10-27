package io.github.hopewang123456.mailbus.adapters.filestore;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * M2a 任务文件仓 — 双栈共享 {dataDir}/tasks/*.json 的读写契约。
 */
class FileTaskRepositoryTest {

    @Test
    void saveFindRoundtripKeepsUnknownFields(@TempDir Path dataDir) {
        FileTaskRepository repo = new FileTaskRepository(dataDir);
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("task_id", "t-001");
        task.put("status", "running");
        task.put("fsm", new LinkedHashMap<>(Map.of("state", "executing", "priority", 50)));
        task.put("python_only_field", Map.of("nested", true)); // 未知字段原样保留
        task.put("created_at", "2026-10-27T01:00:00Z");
        repo.save("t-001", task);

        var found = repo.find("t-001");
        assertTrue(found.isPresent());
        assertEquals("running", found.get().get("status"));
        assertEquals("executing", ((Map<?, ?>) found.get().get("fsm")).get("state"));
        assertEquals(Boolean.TRUE, ((Map<?, ?>) found.get().get("python_only_field")).get("nested"));
        assertTrue(java.nio.file.Files.isRegularFile(dataDir.resolve("tasks/t-001.json")));
    }

    @Test
    void findMissingReturnsEmpty(@TempDir Path dataDir) {
        assertEquals(java.util.Optional.empty(), new FileTaskRepository(dataDir).find("nope"));
    }

    @Test
    void listAllSortedByCreatedAt(@TempDir Path dataDir) {
        FileTaskRepository repo = new FileTaskRepository(dataDir);
        for (String[] idAndTs : new String[][]{
                {"t-b", "2026-10-27T02:00:00Z"}, {"t-a", "2026-10-27T01:00:00Z"}}) {
            repo.save(idAndTs[0], new LinkedHashMap<>(Map.of(
                    "task_id", idAndTs[0], "created_at", idAndTs[1])));
        }
        List<Map<String, Object>> all = repo.listAll();
        assertEquals(2, all.size());
        assertEquals("t-a", all.get(0).get("task_id"));
        assertEquals("t-b", all.get(1).get("task_id"));
    }
}
