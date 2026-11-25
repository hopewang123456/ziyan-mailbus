package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 工作流图校验：与 Python application/workflow/validation 保持同一口径。 */
public final class WorkflowGraphValidator {

    public static final Pattern NODE_ID = Pattern.compile("^[a-z][a-z0-9_]{0,63}$");
    private static final Pattern PROMPT_VAR =
            Pattern.compile("\\{\\{\\s*([^{}]+?)\\s*\\}\\}");
    private static final Pattern CRON = Pattern.compile("[0-9A-Za-z*/,?\\-]+");
    private static final List<String> PROMPT_PREFIXES =
            List.of("task.", "workflow.", "node.", "role.");
    private static final List<String> FIELD_PREFIXES =
            List.of("result.", "task.", "node.", "context.", "artifacts.");
    private static final Set<String> NUMERIC_OPS = Set.of(">=", "<=", ">", "<");
    private static final Set<String> VALID_OPS = Set.of(
            "==", "!=", ">=", "<=", ">", "<", "contains", "in", "not_in",
            "startsWith", "endsWith", "regex");
    private static final ObjectMapper JSON = new ObjectMapper();

    private WorkflowGraphValidator() {
    }

    public record Issue(String code, String messageZh, String nodeId,
                        WorkflowDtos.EdgeRefOut edge) {
    }

    public record Report(List<Issue> errors, List<Issue> warnings,
                         Map<String, Object> stats) {
        public boolean ok() {
            return errors.isEmpty();
        }
    }

    public static List<Issue> structural(List<WorkflowDtos.GraphNode> rawNodes,
                                         List<WorkflowDtos.GraphEdge> rawEdges) {
        List<WorkflowDtos.GraphNode> nodes = safe(rawNodes);
        List<WorkflowDtos.GraphEdge> edges = safe(rawEdges);
        List<Issue> issues = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (WorkflowDtos.GraphNode node : nodes) {
            if (!NODE_ID.matcher(node.nodeId()).matches()) {
                issues.add(new Issue("E_INVALID_NODE_ID",
                        "节点 ID「" + node.nodeId() + "」不合法", node.nodeId(), null));
            }
            if (!seen.add(node.nodeId())) {
                issues.add(new Issue("E_DUPLICATE_NODE_ID",
                        "节点 ID「" + node.nodeId() + "」重复", node.nodeId(), null));
            }
        }
        Set<String> known = new HashSet<>(seen);
        for (WorkflowDtos.GraphEdge edge : edges) {
            if (!known.contains(edge.fromNodeId()) || !known.contains(edge.toNodeId())) {
                issues.add(new Issue("E_DANGLING_EDGE", "连线 " + edge.fromNodeId()
                        + " → " + edge.toNodeId() + " 指向不存在的节点", null, ref(edge)));
            } else if (edge.condition() != null && !edge.condition().isEmpty()
                    && !parsable(edge.condition())) {
                issues.add(new Issue("E_CONDITION_SYNTAX", "连线 " + edge.fromNodeId()
                        + " → " + edge.toNodeId() + " 的条件不是合法 JSON",
                        null, ref(edge)));
            }
        }
        return issues;
    }

    public static Report validate(List<WorkflowDtos.GraphNode> rawNodes,
                                  List<WorkflowDtos.GraphEdge> rawEdges) {
        List<WorkflowDtos.GraphNode> nodes = safe(rawNodes);
        List<WorkflowDtos.GraphEdge> edges = safe(rawEdges);
        List<Issue> errors = new ArrayList<>(structural(nodes, edges));
        List<Issue> warnings = new ArrayList<>();
        Map<String, WorkflowDtos.GraphNode> nodeMap = new LinkedHashMap<>();
        for (WorkflowDtos.GraphNode node : nodes) {
            nodeMap.put(node.nodeId(), node);
        }
        List<WorkflowDtos.GraphEdge> usable = new ArrayList<>();
        for (WorkflowDtos.GraphEdge edge : edges) {
            if (nodeMap.containsKey(edge.fromNodeId())
                    && nodeMap.containsKey(edge.toNodeId())) {
                usable.add(edge);
            }
        }
        Map<String, List<WorkflowDtos.GraphEdge>> graph = adjacency(nodeMap, usable);
        Set<Integer> back = new LinkedHashSet<>();
        for (int index = 0; index < usable.size(); index++) {
            if (isBackEdge(usable.get(index), graph)) {
                back.add(index);
            }
        }
        List<WorkflowDtos.GraphNode> starts = nodes.stream()
                .filter(node -> "start".equals(node.nodeType())).toList();
        List<WorkflowDtos.GraphNode> finals = nodes.stream()
                .filter(node -> "final_approval".equals(node.nodeType())).toList();

        endpoints(errors, starts, finals);
        for (WorkflowDtos.GraphNode node : nodes) {
            checkNode(node, errors, warnings);
        }
        for (WorkflowDtos.GraphEdge edge : usable) {
            checkEdge(edge, nodeMap, starts, errors);
        }
        checkFinals(finals, usable, back, errors);
        checkIndegree(nodeMap, usable, back, errors);
        for (WorkflowDtos.GraphNode node : nodeMap.values()) {
            checkOut(node, graph, errors);
        }
        checkOrphans(nodes, starts, graph, errors);
        checkCycles(nodeMap, usable, errors);

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("node_count", nodes.size());
        stats.put("edge_count", edges.size());
        stats.put("max_depth", starts.isEmpty() ? 0 : maxDepth(starts.get(0).nodeId(), graph));
        stats.put("has_cycle", hasCycle(graph));
        return new Report(errors, warnings, stats);
    }

    public static List<WorkflowDtos.ValidateIssueOut> issues(List<Issue> source) {
        return source.stream().map(issue -> new WorkflowDtos.ValidateIssueOut(
                issue.code(), issue.messageZh(), issue.nodeId(), issue.edge())).toList();
    }

    public static List<Map<String, Object>> details(List<Issue> source) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Issue issue : source) {
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("code", issue.code());
            detail.put("message_zh", issue.messageZh());
            if (issue.nodeId() != null) {
                detail.put("node_id", issue.nodeId());
            }
            if (issue.edge() != null) {
                detail.put("edge", Map.of("from_node_id", issue.edge().fromNodeId(),
                        "to_node_id", issue.edge().toNodeId()));
            }
            result.add(detail);
        }
        return result;
    }

    private static void endpoints(List<Issue> errors, List<WorkflowDtos.GraphNode> starts,
                                  List<WorkflowDtos.GraphNode> finals) {
        if (starts.isEmpty()) {
            errors.add(new Issue("E_MISSING_START", "缺少开始节点", null, null));
        } else if (starts.size() > 1) {
            for (WorkflowDtos.GraphNode node : starts) {
                errors.add(new Issue("E_MULTI_START", "开始节点只能有一个",
                        node.nodeId(), null));
            }
        }
        if (finals.isEmpty()) {
            errors.add(new Issue("E_NO_FINAL", "缺少终验节点", null, null));
        }
    }

    private static void checkNode(WorkflowDtos.GraphNode node, List<Issue> errors,
                                  List<Issue> warnings) {
        String type = node.nodeType();
        if (Set.of("agent", "human", "final_approval").contains(type)
                && !hasText(node.positionId()) && !hasText(assignee(node))) {
            errors.add(new Issue("E_NO_POSITION", "节点「" + node.name() + "」未绑定岗位",
                    node.nodeId(), null));
        }
        String prompt = node.promptTemplate() == null ? "" : node.promptTemplate().strip();
        if ("agent".equals(type) && prompt.isEmpty()) {
            warnings.add(new Issue("W_NO_PROMPT", "节点「" + node.name() + "」没有指令模板",
                    node.nodeId(), null));
        }
        if ("human".equals(type) && prompt.isEmpty()) {
            warnings.add(new Issue("W_HUMAN_NO_PROMPT", "节点「" + node.name() + "」没有任务说明",
                    node.nodeId(), null));
        }
        List<String> unknown = unknownVars(node.promptTemplate());
        if (!unknown.isEmpty()) {
            warnings.add(new Issue("W_PROMPT_UNKNOWN_VAR", "节点「" + node.name()
                    + "」模板含未知变量：" + String.join(", ", unknown), node.nodeId(), null));
        }
        checkFanout(node, errors, warnings);
        if (node.timeoutSeconds() != null && node.timeoutSeconds() > 7 * 24 * 3600) {
            warnings.add(new Issue("W_LONG_TIMEOUT", "节点「" + node.name() + "」超时超过 7 天",
                    node.nodeId(), null));
        }
        if ("start".equals(type)) {
            Issue issue = triggerIssue(node);
            if (issue != null) {
                errors.add(issue);
            }
        }
    }

    private static void checkFanout(WorkflowDtos.GraphNode node, List<Issue> errors,
                                    List<Issue> warnings) {
        Integer size = fanoutSize(node);
        if (size == null) {
            return;
        }
        if (size < 2 || size > 10) {
            errors.add(new Issue("E_FANOUT_INVALID", "节点「" + node.name()
                    + "」扇出人数必须在 2–10 之间", node.nodeId(), null));
        } else if (size > 5) {
            warnings.add(new Issue("W_HIGH_FANOUT", "节点「" + node.name() + "」扇出人数超过 5",
                    node.nodeId(), null));
        }
    }

    private static void checkEdge(WorkflowDtos.GraphEdge edge,
                                  Map<String, WorkflowDtos.GraphNode> nodeMap,
                                  List<WorkflowDtos.GraphNode> starts, List<Issue> errors) {
        if (edge.fromNodeId().equals(edge.toNodeId())) {
            errors.add(new Issue("E_SELF_LOOP", "节点「"
                    + nodeMap.get(edge.fromNodeId()).name() + "」不能连到自己",
                    edge.fromNodeId(), ref(edge)));
        }
        boolean toStart = starts.stream().anyMatch(node -> node.nodeId().equals(edge.toNodeId()));
        if (toStart) {
            errors.add(new Issue("E_START_INBOUND", "开始节点不能有入边",
                    edge.toNodeId(), ref(edge)));
        }
        if (hasText(edge.condition())) {
            errors.addAll(conditionIssues(edge, nodeMap.get(edge.fromNodeId())));
        }
    }

    private static void checkFinals(List<WorkflowDtos.GraphNode> finals,
                                    List<WorkflowDtos.GraphEdge> edges, Set<Integer> back,
                                    List<Issue> errors) {
        Set<String> finalIds = new HashSet<>();
        for (WorkflowDtos.GraphNode node : finals) {
            finalIds.add(node.nodeId());
        }
        for (int index = 0; index < edges.size(); index++) {
            WorkflowDtos.GraphEdge edge = edges.get(index);
            if (finalIds.contains(edge.fromNodeId()) && !back.contains(index)) {
                errors.add(new Issue("E_FINAL_FORWARD", "终验节点「" + nameOf(finals,
                        edge.fromNodeId()) + "」的出边只能是打回", edge.fromNodeId(), ref(edge)));
            }
        }
        for (WorkflowDtos.GraphNode node : finals) {
            List<WorkflowDtos.GraphEdge> rework = new ArrayList<>();
            for (int index = 0; index < edges.size(); index++) {
                WorkflowDtos.GraphEdge edge = edges.get(index);
                if (edge.fromNodeId().equals(node.nodeId()) && back.contains(index)) {
                    rework.add(edge);
                }
            }
            for (int index = 1; index < rework.size(); index++) {
                errors.add(new Issue("E_FINAL_REWORK_EDGES", "终验节点「" + node.name()
                        + "」最多只能有一条回边", node.nodeId(), ref(rework.get(index))));
            }
        }
    }

    private static void checkIndegree(Map<String, WorkflowDtos.GraphNode> nodeMap,
                                      List<WorkflowDtos.GraphEdge> edges, Set<Integer> back,
                                      List<Issue> errors) {
        Map<String, Integer> counts = new HashMap<>();
        for (int index = 0; index < edges.size(); index++) {
            if (!back.contains(index)) {
                counts.merge(edges.get(index).toNodeId(), 1, Integer::sum);
            }
        }
        for (WorkflowDtos.GraphNode node : nodeMap.values()) {
            if (Set.of("start", "parallel_join").contains(node.nodeType())) {
                continue;
            }
            if (counts.getOrDefault(node.nodeId(), 0) > 1) {
                errors.add(new Issue("E_MULTI_IN_REQUIRES_JOIN", "节点「" + node.name()
                        + "」有多条前向入边，请先插入汇聚节点", node.nodeId(), null));
            }
        }
    }

    private static void checkOut(WorkflowDtos.GraphNode node,
                                 Map<String, List<WorkflowDtos.GraphEdge>> graph,
                                 List<Issue> errors) {
        List<WorkflowDtos.GraphEdge> out = graph.getOrDefault(node.nodeId(), List.of());
        if (out.size() >= 2) {
            long conditional = out.stream().filter(edge -> hasText(edge.condition())).count();
            if (conditional > 0 && conditional < out.size()) {
                errors.add(new Issue("E_MIXED_OUT_EDGES", "节点「" + node.name()
                        + "」的出边条件不一致", node.nodeId(), null));
            }
            if (fanoutSize(node) != null) {
                errors.add(new Issue("E_FANOUT_WITH_MULTI_OUT", "节点「" + node.name()
                        + "」开启扇出时只能有一条出边", node.nodeId(), null));
            }
        }
    }

    private static void checkOrphans(List<WorkflowDtos.GraphNode> nodes,
                                     List<WorkflowDtos.GraphNode> starts,
                                     Map<String, List<WorkflowDtos.GraphEdge>> graph,
                                     List<Issue> errors) {
        if (starts.isEmpty()) {
            return;
        }
        Set<String> reached = reachable(starts.get(0).nodeId(), graph);
        for (WorkflowDtos.GraphNode node : nodes) {
            if (!reached.contains(node.nodeId())) {
                errors.add(new Issue("E_ORPHAN_NODE", "节点「" + node.name()
                        + "」无法从开始节点到达", node.nodeId(), null));
            }
        }
    }

    private static void checkCycles(Map<String, WorkflowDtos.GraphNode> nodeMap,
                                    List<WorkflowDtos.GraphEdge> edges, List<Issue> errors) {
        for (Set<String> component : strongComponents(nodeMap, edges)) {
            List<WorkflowDtos.GraphEdge> internal = edges.stream()
                    .filter(edge -> component.contains(edge.fromNodeId())
                            && component.contains(edge.toNodeId())).toList();
            if (component.size() == 1 && internal.isEmpty()) {
                continue;
            }
            if (internal.stream().anyMatch(edge -> hasText(edge.condition()))) {
                continue;
            }
            for (String nodeId : component) {
                WorkflowDtos.GraphNode node = nodeMap.get(nodeId);
                if (node.maxLoops() == 0) {
                    errors.add(new Issue("E_CYCLE_UNCONDITIONAL", "节点「" + node.name()
                            + "」所在环没有条件边且循环上限为 0", nodeId, null));
                }
            }
        }
    }

    private static List<Issue> conditionIssues(WorkflowDtos.GraphEdge edge,
                                               WorkflowDtos.GraphNode source) {
        try {
            JsonNode parsed = JSON.readTree(edge.condition());
            return checkCondition(parsed, edge, source);
        } catch (Exception exception) {
            return List.of();
        }
    }

    private static List<Issue> checkCondition(JsonNode node, WorkflowDtos.GraphEdge edge,
                                              WorkflowDtos.GraphNode source) {
        String where = "连线 " + edge.fromNodeId() + " → " + edge.toNodeId() + " 的条件";
        String nodeId = source == null ? null : source.nodeId();
        if (node == null || !node.isObject()) {
            return List.of(syntax(where, nodeId, edge));
        }
        if (node.has("and") || node.has("or")) {
            JsonNode items = node.has("and") ? node.get("and") : node.get("or");
            if (!items.isArray()) {
                return List.of(syntax(where, nodeId, edge));
            }
            if (items.isEmpty()) {
                return List.of(new Issue("E_CONDITION_EMPTY_GROUP", where + "分组为空",
                        nodeId, ref(edge)));
            }
            List<Issue> issues = new ArrayList<>();
            for (JsonNode item : items) {
                issues.addAll(checkCondition(item, edge, source));
            }
            return issues;
        }
        return checkRule(node, where, nodeId, edge);
    }

    private static List<Issue> checkRule(JsonNode node, String where, String nodeId,
                                         WorkflowDtos.GraphEdge edge) {
        List<Issue> issues = new ArrayList<>();
        String name = node.path("field").asText("");
        if (FIELD_PREFIXES.stream().noneMatch(name::startsWith)) {
            issues.add(new Issue("E_CONDITION_FIELD", where + "的字段不在白名单",
                    nodeId, ref(edge)));
        }
        String op = node.path("op").asText("");
        if (!VALID_OPS.contains(op)) {
            issues.add(new Issue("E_CONDITION_OP", where + "的运算符不合法", nodeId, ref(edge)));
        }
        JsonNode value = node.get("value");
        if (("in".equals(op) || "not_in".equals(op)) && (value == null || !value.isArray())) {
            issues.add(new Issue("E_CONDITION_VALUE", where + "的 in 值必须是数组",
                    nodeId, ref(edge)));
        }
        if ("regex".equals(op)) {
            if (value == null || !value.isTextual()) {
                issues.add(new Issue("E_CONDITION_VALUE", where + "的 regex 必须是字符串",
                        nodeId, ref(edge)));
            } else {
                try {
                    Pattern.compile(value.asText());
                } catch (Exception exception) {
                    issues.add(new Issue("E_CONDITION_VALUE", where + "的 regex 非法",
                            nodeId, ref(edge)));
                }
            }
        }
        if (NUMERIC_OPS.contains(op) && (value == null || !value.isNumber())) {
            issues.add(new Issue("E_CONDITION_VALUE", where + "的数值比较缺少数字",
                    nodeId, ref(edge)));
        }
        return issues;
    }

    private static Issue syntax(String where, String nodeId, WorkflowDtos.GraphEdge edge) {
        return new Issue("E_CONDITION_SYNTAX", where + "结构不合法", nodeId, ref(edge));
    }

    private static String assignee(WorkflowDtos.GraphNode node) {
        Map<String, Object> config = node.config();
        if (config == null) {
            return null;
        }
        Object value = config.get("assignee_id");
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private static Integer fanoutSize(WorkflowDtos.GraphNode node) {
        Map<String, Object> config = node.config();
        if (config == null || !(config.get("fanout") instanceof Map<?, ?> fanout)) {
            return null;
        }
        if (!Boolean.TRUE.equals(fanout.get("enabled"))) {
            return null;
        }
        return fanout.get("size") instanceof Number number ? number.intValue() : -1;
    }

    private static List<String> unknownVars(String template) {
        if (template == null || template.isEmpty()) {
            return List.of();
        }
        List<String> unknown = new ArrayList<>();
        Matcher matcher = PROMPT_VAR.matcher(template);
        while (matcher.find()) {
            String plain = matcher.group(1).strip();
            if ("artifacts".equals(plain) || plain.startsWith("artifacts.")
                    || PROMPT_PREFIXES.stream().anyMatch(plain::startsWith)
                    || unknown.contains(plain)) {
                continue;
            }
            unknown.add(plain);
        }
        return unknown;
    }

    private static Issue triggerIssue(WorkflowDtos.GraphNode node) {
        Map<String, Object> config = node.config();
        if (config == null || !(config.get("trigger") instanceof Map<?, ?> trigger)) {
            return null;
        }
        Object modes = trigger.get("mode");
        List<String> values = new ArrayList<>();
        if (modes instanceof List<?> list) {
            for (Object mode : list) {
                values.add(String.valueOf(mode));
            }
        }
        if (!values.contains("schedule") && !values.contains("cron")) {
            return null;
        }
        Object cron = trigger.get("cron");
        if (!(cron instanceof String text) || !validCron(text)) {
            return new Issue("E_TRIGGER_CRON", "开始节点「" + node.name()
                    + "」启用定时触发但 cron 为空或非法", node.nodeId(), null);
        }
        return null;
    }

    private static boolean validCron(String value) {
        String[] parts = value.split("\\s+");
        if (parts.length != 5) {
            return false;
        }
        for (String part : parts) {
            if (!CRON.matcher(part).matches()) {
                return false;
            }
        }
        return true;
    }

    private static Map<String, List<WorkflowDtos.GraphEdge>> adjacency(
            Map<String, WorkflowDtos.GraphNode> nodes, List<WorkflowDtos.GraphEdge> edges) {
        Map<String, List<WorkflowDtos.GraphEdge>> graph = new LinkedHashMap<>();
        for (String nodeId : nodes.keySet()) {
            graph.put(nodeId, new ArrayList<>());
        }
        for (WorkflowDtos.GraphEdge edge : edges) {
            graph.get(edge.fromNodeId()).add(edge);
        }
        return graph;
    }

    private static boolean isBackEdge(WorkflowDtos.GraphEdge edge,
                                      Map<String, List<WorkflowDtos.GraphEdge>> graph) {
        if (edge.fromNodeId().equals(edge.toNodeId())) {
            return true;
        }
        Set<String> seen = new HashSet<>();
        Deque<String> queue = new ArrayDeque<>();
        seen.add(edge.toNodeId());
        queue.add(edge.toNodeId());
        while (!queue.isEmpty()) {
            String current = queue.poll();
            for (WorkflowDtos.GraphEdge item : graph.getOrDefault(current, List.of())) {
                if (item.toNodeId().equals(edge.fromNodeId())) {
                    return true;
                }
                if (seen.add(item.toNodeId())) {
                    queue.add(item.toNodeId());
                }
            }
        }
        return false;
    }

    private static Set<String> reachable(String start,
                                         Map<String, List<WorkflowDtos.GraphEdge>> graph) {
        Set<String> seen = new HashSet<>();
        Deque<String> queue = new ArrayDeque<>();
        seen.add(start);
        queue.add(start);
        while (!queue.isEmpty()) {
            String current = queue.poll();
            for (WorkflowDtos.GraphEdge edge : graph.getOrDefault(current, List.of())) {
                if (seen.add(edge.toNodeId())) {
                    queue.add(edge.toNodeId());
                }
            }
        }
        return seen;
    }

    private static boolean hasCycle(Map<String, List<WorkflowDtos.GraphEdge>> graph) {
        Set<String> done = new HashSet<>();
        for (String nodeId : graph.keySet()) {
            if (!done.contains(nodeId) && walkCycle(nodeId, graph, new HashSet<>(), done)) {
                return true;
            }
        }
        return false;
    }

    private static boolean walkCycle(String nodeId,
                                     Map<String, List<WorkflowDtos.GraphEdge>> graph,
                                     Set<String> path, Set<String> done) {
        if (!path.add(nodeId)) {
            return true;
        }
        for (WorkflowDtos.GraphEdge edge : graph.getOrDefault(nodeId, List.of())) {
            if (walkCycle(edge.toNodeId(), graph, path, done)) {
                return true;
            }
        }
        path.remove(nodeId);
        done.add(nodeId);
        return false;
    }

    private static List<Set<String>> strongComponents(
            Map<String, WorkflowDtos.GraphNode> nodes, List<WorkflowDtos.GraphEdge> edges) {
        Map<String, List<String>> links = new HashMap<>();
        for (String nodeId : nodes.keySet()) {
            links.put(nodeId, new ArrayList<>());
        }
        for (WorkflowDtos.GraphEdge edge : edges) {
            links.get(edge.fromNodeId()).add(edge.toNodeId());
        }
        Tarjan tarjan = new Tarjan(links);
        for (String nodeId : links.keySet()) {
            if (!tarjan.index.containsKey(nodeId)) {
                tarjan.visit(nodeId);
            }
        }
        return tarjan.components;
    }

    private static int maxDepth(String start,
                                Map<String, List<WorkflowDtos.GraphEdge>> graph) {
        return depth(start, graph, new HashSet<>(), new HashMap<>());
    }

    private static int depth(String nodeId, Map<String, List<WorkflowDtos.GraphEdge>> graph,
                             Set<String> path, Map<String, Integer> memo) {
        if (memo.containsKey(nodeId)) {
            return memo.get(nodeId);
        }
        int best = 1;
        path.add(nodeId);
        for (WorkflowDtos.GraphEdge edge : graph.getOrDefault(nodeId, List.of())) {
            if (!path.contains(edge.toNodeId())) {
                best = Math.max(best, depth(edge.toNodeId(), graph, path, memo) + 1);
            }
        }
        path.remove(nodeId);
        memo.put(nodeId, best);
        return best;
    }

    private static String nameOf(List<WorkflowDtos.GraphNode> nodes, String nodeId) {
        return nodes.stream().filter(node -> node.nodeId().equals(nodeId))
                .map(WorkflowDtos.GraphNode::name).findFirst().orElse(nodeId);
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private static boolean parsable(String value) {
        try {
            JSON.readTree(value);
            return true;
        } catch (Exception exception) {
            return false;
        }
    }

    private static <T> List<T> safe(List<T> value) {
        return value == null ? List.of() : value;
    }

    private static WorkflowDtos.EdgeRefOut ref(WorkflowDtos.GraphEdge edge) {
        return new WorkflowDtos.EdgeRefOut(edge.fromNodeId(), edge.toNodeId());
    }

    private static final class Tarjan {
        private final Map<String, List<String>> links;
        private final Map<String, Integer> index = new HashMap<>();
        private final Map<String, Integer> low = new HashMap<>();
        private final Deque<String> stack = new ArrayDeque<>();
        private final Set<String> onStack = new HashSet<>();
        private final List<Set<String>> components = new ArrayList<>();
        private int counter;

        private Tarjan(Map<String, List<String>> links) {
            this.links = links;
        }

        private void visit(String nodeId) {
            index.put(nodeId, counter);
            low.put(nodeId, counter);
            counter++;
            stack.push(nodeId);
            onStack.add(nodeId);
            for (String target : links.getOrDefault(nodeId, List.of())) {
                if (!index.containsKey(target)) {
                    visit(target);
                    low.put(nodeId, Math.min(low.get(nodeId), low.get(target)));
                } else if (onStack.contains(target)) {
                    low.put(nodeId, Math.min(low.get(nodeId), index.get(target)));
                }
            }
            if (!low.get(nodeId).equals(index.get(nodeId))) {
                return;
            }
            Set<String> component = new LinkedHashSet<>();
            while (true) {
                String current = stack.pop();
                onStack.remove(current);
                component.add(current);
                if (current.equals(nodeId)) {
                    break;
                }
            }
            components.add(component);
        }
    }
}
