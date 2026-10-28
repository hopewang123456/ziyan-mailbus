package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.task.TaskFsmState;
import io.github.hopewang123456.mailbus.infra.json.JsonFiles;
import io.github.hopewang123456.mailbus.ports.TaskRepository;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 子言收件箱聚合 — python {@code handle_command_inbox} 对等（M2c，D1 被唤起侧）：
 * 四路（manager-pending 三桶 + human-queue pending 去重 + 最近告警 + 子言
 * inbox 未读）→ 统一消息流；动作按钮走既有 /api/tasks/{id}/fsm/{action}。
 */
public class CommandInboxService {

    /** python _MP_ACTIONS：bucket/type → 可执行 FSM 动作（label 中文）。 */
    private static final Map<String, List<Object[]>> MP_ACTIONS = Map.of(
            "plan_approval", List.of(new Object[]{"approve-plan", "批准计划"}, new Object[]{"rollback", "回退"}),
            "acceptance", List.of(new Object[]{"accept", "验收"}, new Object[]{"rollback", "回退"}),
            "coordination", List.of(new Object[]{"continue", "继续"}, new Object[]{"rollback", "回退"}));

    private static final Set<String> TERMINAL_MSG_STATES =
            Set.of("done", "closed", "rejected", "failed", "archived", "sent");

    private final Path dataDir;
    private final TaskRepository tasks;
    private final HumanQueueService humanQueue;

    public CommandInboxService(Path dataDir, TaskRepository tasks, HumanQueueService humanQueue) {
        this.dataDir = dataDir;
        this.tasks = tasks;
        this.humanQueue = humanQueue;
    }

    /** GET /api/command/inbox — {status, identity, unread, ziyan_inbox_unread, items}。 */
    public Map<String, Object> inbox() {
        List<Map<String, Object>> items = new ArrayList<>();

        // 1) manager pending（任务池三桶：待批/待终验/待协调）
        for (Map<String, Object> task : tasks.listAll()) {
            String bucket = bucketOf(task);
            if (bucket.isEmpty()) {
                continue;
            }
            String taskId = str(task.get("task_id"));
            Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> f ? toMap(f) : Map.of();
            Map<String, Object> item = baseItem("manager_pending",
                    "mp:" + taskId + ":" + bucket,
                    firstNonEmpty(task.get("updated_at"), task.get("created_at")),
                    (task.get("summary") != null ? str(task.get("summary"))
                            : str(task.get("intent"))) + "（" + taskId + "）",
                    "warn", taskId);
            item.put("actions", actionsOf(bucket, taskId));
            items.add(item);
        }

        // 2) human queue（pending；与 manager-pending 同 task+type 去重；遍历前 50 条）
        List<Map<String, Object>> hqItems = humanQueue.items();
        for (Map<String, Object> it : hqItems.subList(0, Math.min(50, hqItems.size()))) {
            if (!"pending".equals(str(it.get("status")))) {
                continue;
            }
            String itype = str(it.get("type"));
            String taskId = str(it.get("task_id"));
            String dedup = "mp:" + taskId + ":" + itype;
            if (items.stream().anyMatch(i -> dedup.equals(str(i.get("id"))))) {
                continue;
            }
            Map<String, Object> item = baseItem("human_queue",
                    "hq:" + it.get("id"),
                    str(it.get("created_at")),
                    str(it.getOrDefault("title", itype)) + "（" + (taskId.isEmpty() ? str(it.get("id")) : taskId) + "）",
                    "warn", taskId);
            item.put("actions", actionsOf(itype, taskId));
            items.add(item);
        }

        // 3) alerts（{dataDir}/alerts.json 最近 5 条）
        Map<String, Object> alertsDoc = JsonFiles.readMap(dataDir.resolve("alerts.json"));
        if (alertsDoc != null && alertsDoc.get("alerts") instanceof List<?> alerts) {
            int from = Math.max(0, alerts.size() - 5);
            for (Object o : alerts.subList(from, alerts.size())) {
                if (!(o instanceof Map<?, ?> al)) {
                    continue;
                }
                String sev = al.get("severity") == null ? "info" : String.valueOf(al.get("severity"));
                Map<String, Object> item = baseItem("alert",
                        "al:" + al.get("id"),
                        firstNonEmpty(al.get("ts"), al.get("time")),
                        "[" + sev + "] " + firstNonEmpty(al.get("message"), al.get("type")),
                        "critical".equals(sev) ? "critical" : "warn", "");
                item.put("actions", List.of());
                items.add(item);
            }
        }

        // 4) 子言 inbox（未读消息，尾 20 条）
        int ziyanUnread = 0;
        Map<String, Object> inboxDoc = JsonFiles.readMap(dataDir.resolve("inbox/ziyan/inbox.json"));
        if (inboxDoc != null && inboxDoc.get("messages") instanceof List<?> msgs) {
            int from = Math.max(0, msgs.size() - 20);
            for (Object o : msgs.subList(from, msgs.size())) {
                if (!(o instanceof Map<?, ?> m)) {
                    continue;
                }
                String state = firstNonEmpty(m.get("state"), m.get("status"));
                if (TERMINAL_MSG_STATES.contains(state)) {
                    continue;
                }
                ziyanUnread++;
                String content = str(m.get("content"));
                Map<String, Object> item = baseItem("inbox",
                        "in:" + m.get("id"),
                        str(m.get("created_at")),
                        "来自 " + str(m.get("from")) + "：" + (content.length() > 120 ? content.substring(0, 120) : content),
                        "info", "");
                item.put("actions", List.of());
                items.add(item);
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("identity", Map.of("id", "ziyan"));
        out.put("unread", items.size());
        out.put("ziyan_inbox_unread", ziyanUnread);
        out.put("items", items);
        return out;
    }

    /**
     * python {@code _bucket_of} 的 java 对等：
     * accepting→acceptance / await_plan_approval→plan_approval /
     * await_join_review|join_gate_review|blocked|failed→coordination。
     */
    private static String bucketOf(Map<String, Object> task) {
        Map<String, Object> fsm = task.get("fsm") instanceof Map<?, ?> f ? toMap(f) : Map.of();
        String state = str(fsm.get("state"));
        if (TaskFsmState.ACCEPTING.value().equals(state)) {
            return "acceptance";
        }
        if ("await_plan_approval".equals(str(fsm.get("substate")))) {
            return "plan_approval";
        }
        // 2026-10-27 PY4-A：对齐 python——协作评审待批也进 coordination 桶
        if ("await_join_review".equals(str(fsm.get("substate")))
                || "join_gate_review".equals(str(fsm.get("reason")))) {
            return "coordination";
        }
        if (TaskFsmState.BLOCKED.value().equals(state) || TaskFsmState.FAILED.value().equals(state)) {
            return "coordination";
        }
        return "";
    }

    private static List<Map<String, Object>> actionsOf(String bucket, String taskId) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object[] pair : MP_ACTIONS.getOrDefault(bucket, List.of())) {
            Map<String, Object> a = new LinkedHashMap<>();
            a.put("action", pair[0]);
            a.put("label", pair[1]);
            a.put("task_id", taskId);
            out.add(a);
        }
        return out;
    }

    private static Map<String, Object> baseItem(String source, String id, String ts,
                                                String text, String tone, String taskId) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("source", source);
        item.put("id", id);
        item.put("ts", ts);
        item.put("text", text);
        item.put("tone", tone);
        item.put("task_id", taskId);
        return item;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object o) {
        return (Map<String, Object>) o;
    }

    private static String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    private static String firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty()) {
                return String.valueOf(v);
            }
        }
        return "";
    }
}
