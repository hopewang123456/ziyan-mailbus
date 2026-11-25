package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 只读图索引：wf_nodes / wf_node_transitions 的运行时视图。 */
@Component
public class TaskGraph {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public TaskGraph(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public record GraphNode(String nodeId, String name, int seq, String positionId,
                            String nodeType, int maxRetries, int maxLoops,
                            Integer timeoutSeconds, Map<String, Object> config) {
    }

    public record Edge(String fromNodeId, String toNodeId, String condition) {
    }

    public record Index(List<GraphNode> nodes, List<Edge> edges) {

        public GraphNode node(String nodeId) {
            return nodes.stream().filter(item -> item.nodeId().equals(nodeId))
                    .findFirst().orElse(null);
        }

        public List<String> startNodes() {
            List<String> targets = edges.stream().map(Edge::toNodeId).toList();
            List<String> starts = new ArrayList<>();
            for (GraphNode node : nodes) {
                if (!targets.contains(node.nodeId())) {
                    starts.add(node.nodeId());
                }
            }
            if (starts.isEmpty() && !nodes.isEmpty()) {
                starts.add(nodes.get(0).nodeId());
            }
            return starts;
        }

        public List<Edge> forwardEdges(String nodeId) {
            return edges.stream().filter(edge -> edge.fromNodeId().equals(nodeId)).toList();
        }

        public List<Edge> backEdges(String nodeId) {
            return edges.stream().filter(edge -> edge.toNodeId().equals(nodeId)).toList();
        }

        public List<String> predecessors(String nodeId) {
            return edges.stream().filter(edge -> edge.toNodeId().equals(nodeId))
                    .map(Edge::fromNodeId).distinct().toList();
        }
    }

    public Index load(String workflowId, int version) {
        if (workflowId == null) {
            return null;
        }
        List<GraphNode> nodes = jdbc.query("""
                SELECT node_id, name, seq, position_id, node_type, max_retries, max_loops,
                       timeout_seconds, config
                  FROM wf_nodes WHERE workflow_id = ? AND version = ? ORDER BY seq, node_id
                """, (row, index) -> {
            Integer timeout = row.getObject("timeout_seconds") == null
                    ? null : row.getInt("timeout_seconds");
            return new GraphNode(row.getString("node_id"), row.getString("name"),
                    row.getInt("seq"), row.getString("position_id"), row.getString("node_type"),
                    row.getInt("max_retries"), row.getInt("max_loops"), timeout,
                    parseConfig(row.getString("config")));
        }, workflowId, version);
        List<Edge> edges = jdbc.query("""
                SELECT from_node_id, to_node_id, condition FROM wf_node_transitions
                 WHERE workflow_id = ? AND version = ? ORDER BY from_node_id, to_node_id
                """, (row, index) -> new Edge(row.getString("from_node_id"),
                row.getString("to_node_id"), row.getString("condition")), workflowId, version);
        return new Index(nodes, edges);
    }

    private Map<String, Object> parseConfig(String raw) {
        if (raw == null || raw.isBlank()) {
            return Map.of();
        }
        try {
            Map<String, Object> parsed = objectMapper.readValue(raw,
                    new TypeReference<LinkedHashMap<String, Object>>() {
                    });
            return parsed == null ? Map.of() : parsed;
        } catch (Exception exception) {
            return Map.of();
        }
    }
}
