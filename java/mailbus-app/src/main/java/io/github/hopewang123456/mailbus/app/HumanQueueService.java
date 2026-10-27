package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 人工待办队列（{dataDir}/human-queue.json）— python
 * {@code adapters/orchestration/human_queue.py} 最小对等：enqueue 幂等 +
 * closeByTask 置 resolved。M2a 不做 file lock（命令触发的低频写）。
 */
public class HumanQueueService {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("yyyyMMdd");

    private final Path dataDir;
    private final Clock clock;

    public HumanQueueService(Path dataDir, Clock clock) {
        this.dataDir = dataDir;
        this.clock = clock;
    }

    /** 追加待办；task_id+type=plan_approval 已 pending → 返回既有 id（幂等）。 */
    public String enqueue(Map<String, Object> item) {
        Path q = dataDir.resolve("human-queue.json");
        Map<String, Object> doc = JsonFiles.readMap(q);
        if (doc == null) {
            doc = new LinkedHashMap<>();
        }
        List<Map<String, Object>> items = items(doc);
        String qtype = str(item.getOrDefault("type", ""));
        String taskId = str(item.get("task_id"));
        if ("plan_approval".equals(qtype) && !taskId.isEmpty()) {
            for (Map<String, Object> existing : items) {
                if ("pending".equals(str(existing.get("status")))
                        && qtype.equals(str(existing.get("type")))
                        && taskId.equals(str(existing.get("task_id")))) {
                    return str(existing.get("id"));
                }
            }
        }
        Instant now = Instant.now(clock);
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("id", str(item.getOrDefault("id", newId(now))));
        entry.put("type", qtype);
        entry.put("status", item.getOrDefault("status", "pending"));
        entry.put("created_at", item.getOrDefault("created_at", now.toString()));
        entry.put("title", item.getOrDefault("title", qtype));
        item.forEach((k, v) -> entry.putIfAbsent(k, v)); // hint/task_id/context 等透传
        items.add(entry);
        doc.put("version", doc.getOrDefault("version", "1.0.0"));
        doc.put("items", items);
        doc.put("updated_at", now.toString());
        JsonFiles.write(q, doc);
        return str(entry.get("id"));
    }

    /** 全量条目读取（M2c command/inbox 聚合消费；无文件返回空表）。 */
    public List<Map<String, Object>> items() {
        Map<String, Object> doc = JsonFiles.readMap(dataDir.resolve("human-queue.json"));
        return doc == null ? new ArrayList<>() : items(doc);
    }

    /** 该任务指定类型的 pending 条目 → resolved + resolution；qtype 空 = 匹配任意类型（任务终态收尾）。 */
    public void closeByTask(String taskId, String qtype, Map<String, Object> resolution) {
        Path q = dataDir.resolve("human-queue.json");
        Map<String, Object> doc = JsonFiles.readMap(q);
        if (doc == null) {
            return;
        }
        List<Map<String, Object>> items = items(doc);
        boolean changed = false;
        for (Map<String, Object> item : items) {
            if (!"pending".equals(str(item.get("status")))
                    || !taskId.equals(str(item.get("task_id")))) {
                continue;
            }
            if (qtype != null && !qtype.isEmpty() && !qtype.equals(str(item.get("type")))) {
                continue;
            }
            item.put("status", "resolved");
            item.put("resolved_at", Instant.now(clock).toString());
            if (resolution != null) {
                item.put("resolution", resolution);
            }
            changed = true;
        }
        if (changed) {
            doc.put("items", items);
            doc.put("updated_at", Instant.now(clock).toString());
            JsonFiles.write(q, doc);
        }
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> items(Map<String, Object> doc) {
        Object obj = doc.get("items");
        if (obj instanceof List<?> l) {
            return (List<Map<String, Object>>) (List<?>) l;
        }
        return new ArrayList<>();
    }

    private static String newId(Instant now) {
        return "hq-" + DAY.format(now.atZone(ZoneOffset.UTC))
                + "-" + String.format("%06x", RANDOM.nextInt(0xffffff));
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }
}
