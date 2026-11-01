package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 任务回放与演练（java 机制深化批四，2026-10-30）— python 对等：
 * task_trace 生命周期回放时序（E9）、drill video-publish check-n8n 探测。
 */
public class TaskTraceService {

    private static final Map<String, Integer> PHASE_ORDER = Map.of(
            "created", 0, "planned", 1, "dispatched", 2, "delivered", 3,
            "step_done", 4, "accepted", 5, "blocked", 6, "terminal", 7, "note", 8);

    private final Path dataDir;
    private final TaskRepository tasks;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).build();

    public TaskTraceService(Path dataDir, TaskRepository tasks) {
        this.dataDir = dataDir;
        this.tasks = tasks;
    }

    /** python task_trace：E9 生命周期回放时序。 */
    public Map<String, Object> trace(String taskId) {
        var found = tasks.find(taskId);
        if (found.isEmpty()) {
            throw new IllegalArgumentException("unknown task: " + taskId);
        }
        Map<String, Object> task = found.get();
        List<Map<String, Object>> events = new ArrayList<>();

        add(events, str(task.get("created_at")), "created",
                strOr(task.get("initiator"), "human"),
                "建单：" + truncate(str(task.get("intent")), 60), "task");

        Map<String, Object> pm = task.get("plan_meta") instanceof Map<?, ?> m ? cast(m) : Map.of();
        if (!pm.isEmpty()) {
            List<?> chain = task.get("chain") instanceof List<?> l ? l : List.of();
            add(events, str(task.get("created_at")), "planned", "planner",
                    "规划方法 " + str(pm.get("method")) + " · " + chain.size() + " 步", "task.plan_meta");
        }
        for (Object o : task.get("events") instanceof List<?> l ? l : List.of()) {
            if (!(o instanceof Map<?, ?> eRaw)) {
                continue;
            }
            Map<String, Object> e = cast(eRaw);
            String action = str(e.get("action"));
            String phase = "note";
            for (var kv : List.of(
                    Map.entry("dispatch", "dispatched"), Map.entry("accept", "accepted"),
                    Map.entry("blocked", "blocked"), Map.entry("verify", "note"))) {
                if (action.contains(kv.getKey())) {
                    phase = kv.getValue();
                    break;
                }
            }
            String note = str(e.get("note"));
            add(events, str(e.get("ts")), phase, strOr(e.get("actor"), "system"),
                    action + (note.isEmpty() ? "" : " · " + truncate(note, 60)), "task.events");
        }

        // 步骤生命周期
        java.util.Set<String> chainAgents = new java.util.HashSet<>();
        for (Object o : task.get("chain") instanceof List<?> l ? l : List.of()) {
            if (!(o instanceof Map<?, ?> sRaw)) {
                continue;
            }
            Map<String, Object> s = cast(sRaw);
            String sid = str(s.get("step_id"));
            String agent = !str(s.get("to_agent")).isEmpty() ? str(s.get("to_agent")) : str(s.get("to_person"));
            String station = str(s.get("station"));
            String who = (!station.isEmpty() ? station + (agent.isEmpty() ? "" : "→") : "") + agent;
            if (who.isEmpty()) {
                who = "?";
            }
            if (!agent.isEmpty()) {
                chainAgents.add(agent);
            }
            add(events, str(s.get("started_at")), "dispatched", who,
                    "步骤 " + sid + " 派工" + (station.isEmpty() ? "" : "（工位 " + station + "）"), "task.chain");

            for (Object a : s.get("transport_attempts") instanceof List<?> al ? al : List.of()) {
                if (a instanceof Map<?, ?> att && str(((Map<?, ?>) a).get("ts")).isEmpty() == false) {
                    Map<?, ?> am = (Map<?, ?>) a;
                    add(events, str(am.get("ts")), "delivered", who,
                            "投递通道 " + str(am.get("channel")) + " · " + str(am.get("outcome")),
                            "step.transport_attempts");
                }
            }

            String resultTs = stepResultTs(taskId, sid);
            if (!resultTs.isEmpty()) {
                add(events, resultTs, "step_done", agent,
                        "步骤 " + sid + " 回执（" + strOr(s.get("fsm_state"), str(s.get("status"))) + "）",
                        "msg-results");
            }
            add(events, str(s.get("completed_at")), "step_done", agent,
                    "步骤 " + sid + " 完成", "task.chain");
        }

        // 验收
        Map<String, Object> acc = task.get("acceptance_record") instanceof Map<?, ?> am ? cast(am) : Map.of();
        if (!acc.isEmpty()) {
            String ts = !str(acc.get("resolved_at")).isEmpty() ? str(acc.get("resolved_at")) : str(acc.get("ts"));
            add(events, ts, "accepted", str(acc.get("reviewer")),
                    "验收 " + str(acc.get("decision")) + "（" + str(acc.get("method")) + "）", "acceptance");
        }

        String status = str(task.get("status"));
        String phase = status.equals("success") || status.equals("cancelled") ? "terminal"
                : status.equals("blocked") ? "blocked" : "note";
        Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> fm ? cast(fm) : Map.of();
        add(events, str(task.get("updated_at")), phase, "system",
                "当前状态 " + status + (status.equals("blocked") && !str(fsm.get("reason")).isEmpty()
                        ? " · " + str(fsm.get("reason")) : ""), "task.status");

        // 排序
        events.sort(Comparator
                .comparing((Map<String, Object> e) -> str(e.get("ts")))
                .thenComparing(e -> PHASE_ORDER.getOrDefault(str(e.get("phase")), 9)));

        // steps 摘要
        List<Map<String, Object>> steps = new ArrayList<>();
        for (Object o : task.get("chain") instanceof List<?> l ? l : List.of()) {
            if (o instanceof Map<?, ?> sRaw) {
                Map<String, Object> s = cast(sRaw);
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("step_id", s.get("step_id"));
                row.put("station", strOr(s.get("station"), ""));
                row.put("to_agent", strOr(s.get("to_agent"), str(s.get("to_person"))));
                row.put("fsm_state", strOr(s.get("fsm_state"), str(s.get("status"))));
                steps.add(row);
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("task_id", taskId);
        out.put("status", status);
        out.put("intent", truncate(str(task.get("intent")), 120));
        out.put("steps", steps);
        out.put("events", events);
        return out;
    }

    /** msg-results/<taskId>/step-<sid>.json 的 mtime（python _step_result_ts 近似）。 */
    private String stepResultTs(String taskId, String stepId) {
        Path p = dataDir.resolve("msg-results").resolve(taskId).resolve("step-" + stepId + ".json");
        if (!Files.isRegularFile(p)) {
            return "";
        }
        try {
            return java.time.Instant.ofEpochMilli(Files.getLastModifiedTime(p).toMillis())
                    .atZone(java.time.ZoneId.systemDefault())
                    .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"));
        } catch (IOException ignored) {
            return "";
        }
    }

    /** python probe_n8n_webhook：N8N_PUBLISH_WEBHOOK_URL 可达性探测。 */
    public Map<String, Object> probeN8nWebhook(String url) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (url == null || url.isBlank()) {
            out.put("ok", false);
            out.put("error", "N8N_PUBLISH_WEBHOOK_URL 未配置");
            return out;
        }
        out.put("url", url);
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString("{\"probe\": true}"))
                    .build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            out.put("ok", resp.statusCode() >= 200 && resp.statusCode() < 500);
            out.put("status", resp.statusCode());
        } catch (Exception e) {
            out.put("ok", false);
            out.put("error", String.valueOf(e.getMessage()));
        }
        return out;
    }

    private static void add(List<Map<String, Object>> events, String ts, String phase,
                            String actor, String detail, String source) {
        if (ts == null || ts.isEmpty()) {
            return;
        }
        Map<String, Object> e = new LinkedHashMap<>();
        e.put("ts", ts.length() > 19 ? ts.substring(0, 19) : ts);
        e.put("phase", phase);
        e.put("actor", actor);
        e.put("detail", detail);
        e.put("source", source);
        events.add(e);
    }

    private static String truncate(String s, int n) {
        return s.length() > n ? s.substring(0, n) : s;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static String strOr(Object o, String fallback) {
        String s = str(o);
        return s.isEmpty() ? fallback : s;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Map<?, ?> m) {
        return (Map<String, Object>) m;
    }
}
