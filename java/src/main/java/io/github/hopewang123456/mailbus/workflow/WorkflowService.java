package io.github.hopewang123456.mailbus.workflow;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Service
public class WorkflowService {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final ObjectMapper objectMapper;
    private final Outbox outbox;

    public WorkflowService(JdbcTemplate jdbc, Ids ids, ObjectMapper objectMapper, Outbox outbox) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.objectMapper = objectMapper;
        this.outbox = outbox;
    }

    public List<WorkflowDtos.WorkflowOut> list() {
        return jdbc.query("SELECT * FROM wf_defs ORDER BY created_at", this::mapDefinition);
    }

    public WorkflowDtos.WorkflowOut get(String workflowId) {
        return loadDefinition(workflowId);
    }

    @Transactional
    public WorkflowDtos.WorkflowOut create(Actor actor, WorkflowDtos.WorkflowIn input) {
        Authz.require(actor, Authz.WORKFLOW_CREATE);
        String name = validName(input.name(), "流程名称");
        String workflowId = ids.next("wf");
        jdbc.update("""
                INSERT INTO wf_defs (workflow_id, name, latest_version, published_version, created_at)
                VALUES (?, ?, 0, NULL, ?)
                """, workflowId, name, Instant.now().getEpochSecond());
        outbox.enqueue("workflow.created", java.util.Map.of("workflow_id", workflowId));
        return loadDefinition(workflowId);
    }

    @Transactional
    public WorkflowDtos.WorkflowOut rename(Actor actor, String workflowId,
                                           WorkflowDtos.WorkflowIn input) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        loadDefinition(workflowId);
        String name = validName(input.name(), "流程名称");
        jdbc.update("UPDATE wf_defs SET name = ? WHERE workflow_id = ?", name, workflowId);
        outbox.enqueue("workflow.renamed", java.util.Map.of("workflow_id", workflowId,
                "name", name));
        return loadDefinition(workflowId);
    }

    @Transactional
    public void delete(Actor actor, String workflowId) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        loadDefinition(workflowId);
        Integer used = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_tasks WHERE workflow_id = ?", Integer.class, workflowId);
        if (used != null && used > 0) {
            throw ApiException.conflict("invalid_state", "已有任务引用该流程，不能删除");
        }
        jdbc.update("DELETE FROM wf_versions WHERE workflow_id = ?", workflowId);
        jdbc.update("DELETE FROM wf_defs WHERE workflow_id = ?", workflowId);
        outbox.enqueue("workflow.deleted", java.util.Map.of("workflow_id", workflowId));
    }

    public List<WorkflowDtos.VersionOut> versions(String workflowId) {
        loadDefinition(workflowId);
        return jdbc.query("SELECT * FROM wf_versions WHERE workflow_id = ? ORDER BY version",
                this::mapVersion, workflowId);
    }

    public WorkflowDtos.VersionOut version(String workflowId, int version) {
        loadDefinition(workflowId);
        return loadVersion(workflowId, version);
    }

    @Transactional
    public WorkflowDtos.VersionOut addVersion(Actor actor, String workflowId,
                                              WorkflowDtos.VersionIn input) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        WorkflowDtos.WorkflowOut definition = loadDefinition(workflowId);
        List<WorkflowDtos.VersionNodeOut> nodes = new ArrayList<>();
        int index = 0;
        for (WorkflowDtos.VersionNodeIn node : input.nodes()) {
            String name = validName(node.name(), "节点名称");
            nodes.add(new WorkflowDtos.VersionNodeOut(ids.next("node"), name, index++));
        }
        int version = definition.latestVersion() + 1;
        Instant now = Instant.now();
        jdbc.update("""
                INSERT INTO wf_versions (workflow_id, version, state, nodes, created_at)
                VALUES (?, ?, 'draft', ?, ?)
                """, workflowId, version, json(nodes), now.getEpochSecond());
        jdbc.update("UPDATE wf_defs SET latest_version = ? WHERE workflow_id = ?",
                version, workflowId);
        outbox.enqueue("workflow.version_created", java.util.Map.of(
                "workflow_id", workflowId, "version", version));
        return loadVersion(workflowId, version);
    }

    @Transactional
    public WorkflowDtos.VersionOut publish(Actor actor, String workflowId, int versionNumber) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        WorkflowDtos.WorkflowOut definition = loadDefinition(workflowId);
        WorkflowDtos.VersionOut version = loadVersion(workflowId, versionNumber);
        if ("published".equals(version.state())) {
            return version;
        }
        Instant now = Instant.now();
        jdbc.update("""
                UPDATE wf_versions SET state = 'published', published_at = ?
                 WHERE workflow_id = ? AND version = ?
                """, now.getEpochSecond(), workflowId, versionNumber);
        int pointer = Math.max(definition.publishedVersion() == null
                ? 0 : definition.publishedVersion(), versionNumber);
        jdbc.update("UPDATE wf_defs SET published_version = ? WHERE workflow_id = ?",
                pointer, workflowId);
        outbox.enqueue("workflow.version_published", java.util.Map.of(
                "workflow_id", workflowId, "version", versionNumber));
        return loadVersion(workflowId, versionNumber);
    }

    public WorkflowDtos.VersionOut loadVersion(String workflowId, int version) {
        List<WorkflowDtos.VersionOut> rows = jdbc.query(
                "SELECT * FROM wf_versions WHERE workflow_id = ? AND version = ?",
                this::mapVersion, workflowId, version);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("流程版本不存在"));
    }

    public WorkflowDtos.WorkflowOut loadDefinition(String workflowId) {
        List<WorkflowDtos.WorkflowOut> rows = jdbc.query(
                "SELECT * FROM wf_defs WHERE workflow_id = ?", this::mapDefinition, workflowId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("流程不存在"));
    }

    private WorkflowDtos.WorkflowOut mapDefinition(java.sql.ResultSet row, int index)
            throws java.sql.SQLException {
        int published = row.getInt("published_version");
        boolean publishedNull = row.wasNull();
        return new WorkflowDtos.WorkflowOut(
                row.getString("workflow_id"), row.getString("name"),
                row.getInt("latest_version"), publishedNull ? null : published,
                Instant.ofEpochSecond((long) row.getDouble("created_at")));
    }

    private WorkflowDtos.VersionOut mapVersion(java.sql.ResultSet row, int index)
            throws java.sql.SQLException {
        double publishedAt = row.getDouble("published_at");
        boolean publishedNull = row.wasNull();
        return new WorkflowDtos.VersionOut(
                row.getString("workflow_id"), row.getInt("version"), row.getString("state"),
                parseNodes(row.getString("nodes")),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                publishedNull ? null : Instant.ofEpochSecond((long) publishedAt));
    }

    private List<WorkflowDtos.VersionNodeOut> parseNodes(String value) {
        try {
            return objectMapper.readValue(value == null ? "[]" : value,
                    new TypeReference<List<WorkflowDtos.VersionNodeOut>>() {
                    });
        } catch (Exception exception) {
            return List.of();
        }
    }

    private String validName(String value, String label) {
        String name = value == null ? "" : value.strip();
        if (name.isEmpty()) {
            throw ApiException.conflict("invalid_state", label + "不能为空");
        }
        if (name.length() > 64) {
            throw ApiException.conflict("invalid_state", label + "不能超过 64 个字符");
        }
        return name;
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            return "[]";
        }
    }
}
