package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.infra.json.JsonFiles;

import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 工作流模板 registry — python {@code api/handlers_workflows.py} +
 * {@code workflow/registry.py} 对等（交接③，D13 双栈对等）。
 * SoT：{dataDir}/workflows/registry.json（双栈共享；config.mailbus_workflow.
 * registry_path 可覆盖，store/ 前缀相对 store 父目录——python 同语义）。
 */
public class WorkflowsService {

    private static final Pattern VALID_ID = Pattern.compile("^[a-z][a-z0-9_]{1,63}$");

    private final Path dataDir;
    private final Clock clock;

    public WorkflowsService(Path dataDir, Clock clock) {
        this.dataDir = dataDir;
        this.clock = clock;
    }

    private Path registryPath() {
        Map<String, Object> config = JsonFiles.readMap(dataDir.resolve("config.json"));
        if (config != null && config.get("mailbus_workflow") instanceof Map<?, ?> wf) {
            Object rel = ((Map<?, ?>) wf).get("registry_path");
            if (rel instanceof String s && !s.isBlank()) {
                Path p = s.startsWith("store/")
                        ? dataDir.toAbsolutePath().getParent().resolve(s.substring("store/".length()))
                        : dataDir.resolve(s);
                if (java.nio.file.Files.isRegularFile(p)) {
                    return p;
                }
            }
        }
        return dataDir.resolve("workflows/registry.json");
    }

    private Map<String, Object> loadRegistry() {
        Map<String, Object> doc = JsonFiles.readMap(registryPath());
        return doc == null ? new LinkedHashMap<>() : doc;
    }

    private Path saveRegistry(Map<String, Object> registry) {
        registry.put("updated_at", LocalDate.now(clock).toString());
        Path p = registryPath();
        JsonFiles.write(p, registry);
        return p;
    }

    /** GET /api/workflows — 摘要清单（python handle_workflows_list 对等形状）。 */
    public Map<String, Object> list() {
        Map<String, Object> reg = loadRegistry();
        List<Map<String, Object>> items = new ArrayList<>();
        Object workflows = reg.get("workflows");
        if (workflows instanceof Map<?, ?> map) {
            map.forEach((id, wf) -> {
                if (wf instanceof Map<?, ?> w) {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("id", String.valueOf(id));
                    item.put("version", w.get("version"));
                    item.put("display", w.get("display"));
                    item.put("mode", w.get("mode"));
                    item.put("task_types", w.get("task_types") instanceof List<?> l ? l : List.of());
                    item.put("tags", w.get("tags") instanceof List<?> l ? l : List.of());
                    item.put("ui", w.get("ui"));
                    item.put("phase_count", w.get("phases") instanceof List<?> l ? l.size() : 0);
                    item.put("gate_count", w.get("gates") instanceof List<?> l ? l.size() : 0);
                    items.add(item);
                }
            });
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("version", reg.get("version"));
        out.put("updated_at", reg.get("updated_at"));
        out.put("workflows", items);
        return out;
    }

    /** GET /api/workflows/{id}；不存在返回 null（controller 映射 404）。 */
    public Map<String, Object> get(String workflowId) {
        Object wf = workflowsMap().get(workflowId);
        return wf instanceof Map<?, ?> m ? new LinkedHashMap<>((Map<String, Object>) m) : null;
    }

    /** POST /api/workflows/{id} — 创建或更新；返回 {workflow_id, created} 或错误串。 */
    public Map<String, Object> save(String workflowId, Map<String, Object> workflow) {
        if (workflow == null || workflow.isEmpty()) {
            return error("workflow object required");
        }
        String id = String.valueOf(firstNonEmpty(workflow.get("id"), workflowId)).trim();
        if (!VALID_ID.matcher(id).matches()) {
            return error("invalid workflow id");
        }
        workflow.put("id", id);
        Map<String, Object> reg = loadRegistry();
        Map<String, Object> workflows = workflowsMapOf(reg);
        boolean created = !workflows.containsKey(id);
        workflows.put(id, workflow);
        reg.put("workflows", workflows);
        saveRegistry(reg);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("workflow_id", id);
        out.put("created", created);
        return out;
    }

    /** POST /api/workflows/{id}/delete；不存在返回 not_found 错误。 */
    public Map<String, Object> delete(String workflowId) {
        if (!VALID_ID.matcher(workflowId).matches()) {
            return error("invalid id");
        }
        Map<String, Object> reg = loadRegistry();
        Map<String, Object> workflows = workflowsMapOf(reg);
        if (!workflows.containsKey(workflowId)) {
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("status", "error");
            out.put("error", "not_found");
            out.put("__http", 404);
            return out;
        }
        workflows.remove(workflowId);
        reg.put("workflows", workflows);
        saveRegistry(reg);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "ok");
        out.put("deleted", workflowId);
        return out;
    }

    public static boolean isOk(Map<String, Object> out) {
        return "ok".equals(String.valueOf(out.get("status")));
    }

    public static int httpOf(Map<String, Object> out) {
        return out.get("__http") instanceof Number n ? n.intValue() : 200;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> workflowsMap() {
        return workflowsMapOf(loadRegistry());
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> workflowsMapOf(Map<String, Object> reg) {
        Object obj = reg.get("workflows");
        if (obj instanceof Map<?, ?> m) {
            return (Map<String, Object>) m;
        }
        Map<String, Object> empty = new LinkedHashMap<>();
        reg.put("workflows", empty);
        return empty;
    }

    private static Map<String, Object> error(String msg) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "error");
        out.put("error", msg);
        out.put("__http", 400);
        return out;
    }

    private static Object firstNonEmpty(Object... values) {
        for (Object v : values) {
            if (v != null && !String.valueOf(v).isEmpty() && !"null".equals(String.valueOf(v))) {
                return v;
            }
        }
        return null;
    }
}
