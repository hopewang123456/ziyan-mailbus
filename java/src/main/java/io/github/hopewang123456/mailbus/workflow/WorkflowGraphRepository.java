package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;

/** Graph 唯一落点：wf_nodes + wf_node_transitions。 */
@Repository
public class WorkflowGraphRepository {

    private static final String NODE_COLUMNS =
            "workflow_id, version, node_id, name, seq, position_id, node_type,"
                    + " prompt_template, needs_artifacts_from, max_retries, max_loops,"
                    + " timeout_seconds, config, pos_x, pos_y";

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public WorkflowGraphRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public WorkflowDtos.WorkflowGraph load(String workflowId, int version) {
        List<WorkflowDtos.GraphNode> nodes = jdbc.query(
                "SELECT * FROM wf_nodes WHERE workflow_id = ? AND version = ?"
                        + " ORDER BY seq, node_id", this::mapNode, workflowId, version);
        List<WorkflowDtos.GraphEdge> edges = jdbc.query(
                "SELECT * FROM wf_node_transitions WHERE workflow_id = ? AND version = ?"
                        + " ORDER BY from_node_id, to_node_id", this::mapEdge,
                workflowId, version);
        return new WorkflowDtos.WorkflowGraph(nodes, edges);
    }

    public void replace(String workflowId, int version, WorkflowDtos.WorkflowGraph graph) {
        jdbc.update("DELETE FROM wf_node_transitions WHERE workflow_id = ? AND version = ?",
                workflowId, version);
        jdbc.update("DELETE FROM wf_nodes WHERE workflow_id = ? AND version = ?",
                workflowId, version);
        for (WorkflowDtos.GraphNode node : safe(graph.nodes())) {
            jdbc.update("INSERT INTO wf_nodes (" + NODE_COLUMNS + ") VALUES"
                            + " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    workflowId, version, node.nodeId(), node.name(), node.seq(),
                    node.positionId(), node.nodeType(), node.promptTemplate(),
                    json(node.needsArtifactsFrom() == null ? List.of()
                            : node.needsArtifactsFrom()),
                    node.maxRetries(), node.maxLoops(), node.timeoutSeconds(),
                    node.config() == null || node.config().isEmpty() ? null
                            : json(node.config()),
                    node.posX(), node.posY());
        }
        for (WorkflowDtos.GraphEdge edge : safe(graph.edges())) {
            jdbc.update("INSERT INTO wf_node_transitions (workflow_id, version,"
                            + " from_node_id, to_node_id, condition) VALUES (?, ?, ?, ?, ?)",
                    workflowId, version, edge.fromNodeId(), edge.toNodeId(),
                    edge.condition());
        }
    }

    public void copy(String workflowId, int sourceVersion, int targetVersion) {
        jdbc.update("INSERT INTO wf_nodes (" + NODE_COLUMNS + ")"
                        + " SELECT workflow_id, ?, node_id, name, seq, position_id, node_type,"
                        + " prompt_template, needs_artifacts_from, max_retries, max_loops,"
                        + " timeout_seconds, config, pos_x, pos_y FROM wf_nodes"
                        + " WHERE workflow_id = ? AND version = ?",
                targetVersion, workflowId, sourceVersion);
        jdbc.update("INSERT INTO wf_node_transitions (workflow_id, version, from_node_id,"
                        + " to_node_id, condition) SELECT workflow_id, ?, from_node_id,"
                        + " to_node_id, condition FROM wf_node_transitions"
                        + " WHERE workflow_id = ? AND version = ?",
                targetVersion, workflowId, sourceVersion);
    }

    public int bumpRevision(String workflowId, int version) {
        jdbc.update("UPDATE wf_versions SET revision = revision + 1"
                + " WHERE workflow_id = ? AND version = ?", workflowId, version);
        Integer value = jdbc.queryForObject("SELECT revision FROM wf_versions"
                + " WHERE workflow_id = ? AND version = ?", Integer.class, workflowId, version);
        return value == null ? 0 : value;
    }

    public int revision(String workflowId, int version) {
        Integer value = jdbc.queryForObject("SELECT revision FROM wf_versions"
                + " WHERE workflow_id = ? AND version = ?", Integer.class, workflowId, version);
        return value == null ? 0 : value;
    }

    private WorkflowDtos.GraphNode mapNode(ResultSet row, int index) throws SQLException {
        String raw = row.getString("config");
        Map<String, Object> config = raw == null || raw.isEmpty() ? Map.of()
                : read(raw, new TypeReference<Map<String, Object>>() {
                });
        List<String> needs = read(row.getString("needs_artifacts_from"),
                new TypeReference<List<String>>() {
                });
        int timeout = row.getInt("timeout_seconds");
        Integer timeoutValue = row.wasNull() ? null : timeout;
        return new WorkflowDtos.GraphNode(row.getString("node_id"), row.getString("name"),
                row.getString("node_type"), row.getString("position_id"), row.getInt("seq"),
                row.getString("prompt_template"), needs, row.getInt("max_retries"),
                row.getInt("max_loops"), timeoutValue, config, row.getDouble("pos_x"),
                row.getDouble("pos_y"));
    }

    private WorkflowDtos.GraphEdge mapEdge(ResultSet row, int index) throws SQLException {
        return new WorkflowDtos.GraphEdge(row.getString("from_node_id"),
                row.getString("to_node_id"), row.getString("condition"));
    }

    private <T> T read(String raw, TypeReference<T> type) {
        if (raw == null || raw.isEmpty()) {
            try {
                return objectMapper.readValue("[]", type);
            } catch (Exception exception) {
                return null;
            }
        }
        try {
            return objectMapper.readValue(raw, type);
        } catch (Exception exception) {
            return null;
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            return "[]";
        }
    }

    private static <T> List<T> safe(List<T> value) {
        return value == null ? List.of() : value;
    }
}
