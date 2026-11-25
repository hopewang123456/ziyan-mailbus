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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class WorkflowService {

    private final JdbcTemplate jdbc;
    private final Ids ids;
    private final ObjectMapper objectMapper;
    private final Outbox outbox;
    private final WorkflowGraphRepository graphs;

    public WorkflowService(JdbcTemplate jdbc, Ids ids, ObjectMapper objectMapper, Outbox outbox,
                           WorkflowGraphRepository graphs) {
        this.jdbc = jdbc;
        this.ids = ids;
        this.objectMapper = objectMapper;
        this.outbox = outbox;
        this.graphs = graphs;
    }

    public WorkflowDtos.WorkflowListOut list(int limit, int offset) {
        List<WorkflowDtos.WorkflowOut> items = jdbc.query(
                "SELECT * FROM wf_defs WHERE deleted_at IS NULL"
                        + " ORDER BY created_at, workflow_id LIMIT ? OFFSET ?",
                this::mapDefinition, limit, offset);
        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM wf_defs WHERE deleted_at IS NULL", Integer.class);
        return new WorkflowDtos.WorkflowListOut(items, total == null ? 0 : total,
                limit, offset);
    }

    public WorkflowDtos.WorkflowOut get(String workflowId) {
        return loadDefinition(workflowId);
    }

    @Transactional
    public WorkflowDtos.WorkflowOut create(Actor actor, WorkflowDtos.WorkflowIn input) {
        Authz.require(actor, Authz.WORKFLOW_CREATE);
        String name = validName(input.name(), "流程名称");
        WorkflowDtos.WorkflowGraph graph = input.graph();
        if (graph != null) {
            requireStructural(graph);
        }
        String workflowId = ids.next("wf");
        jdbc.update("""
                INSERT INTO wf_defs (workflow_id, name, latest_version, published_version, created_at)
                VALUES (?, ?, 0, NULL, ?)
                """, workflowId, name, Instant.now().getEpochSecond());
        if (graph != null) {
            Instant now = Instant.now();
            jdbc.update("""
                    INSERT INTO wf_versions (workflow_id, version, state, nodes, revision,
                    created_at) VALUES (?, 1, 'draft', '[]', 1, ?)
                    """, workflowId, now.getEpochSecond());
            graphs.replace(workflowId, 1, graph);
            jdbc.update("UPDATE wf_defs SET latest_version = 1 WHERE workflow_id = ?",
                    workflowId);
            outbox.enqueue("workflow.version_created", Map.of(
                    "workflow_id", workflowId, "version", 1));
        }
        outbox.enqueue("workflow.created", Map.of("workflow_id", workflowId));
        return loadDefinition(workflowId);
    }

    @Transactional
    public WorkflowDtos.WorkflowOut rename(Actor actor, String workflowId,
                                           WorkflowDtos.WorkflowIn input) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        loadDefinition(workflowId);
        String name = validName(input.name(), "流程名称");
        jdbc.update("UPDATE wf_defs SET name = ? WHERE workflow_id = ?", name, workflowId);
        outbox.enqueue("workflow.renamed", Map.of("workflow_id", workflowId, "name", name));
        return loadDefinition(workflowId);
    }

    @Transactional
    public void delete(Actor actor, String workflowId) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        loadDefinition(workflowId);
        Integer active = jdbc.queryForObject("SELECT COUNT(*) FROM task_tasks"
                + " WHERE workflow_id = ? AND state NOT IN ('done', 'failed', 'cancelled')",
                Integer.class, workflowId);
        if (active != null && active > 0) {
            throw ApiException.invalid("已有活跃任务引用该流程，不能删除");
        }
        jdbc.update("UPDATE wf_defs SET deleted_at = ?, deleted_by = ?"
                        + " WHERE workflow_id = ? AND deleted_at IS NULL",
                Instant.now().getEpochSecond(), actor.employeeId(), workflowId);
        audit(actor, "workflow.deleted", "workflow:" + workflowId,
                Map.of("workflow_id", workflowId));
        outbox.enqueue("workflow.deleted", Map.of("workflow_id", workflowId));
    }

    public WorkflowDtos.VersionListOut versions(String workflowId, int limit, int offset) {
        loadDefinition(workflowId);
        List<WorkflowDtos.ContractVersionOut> items = jdbc.query(
                "SELECT * FROM wf_versions WHERE workflow_id = ? ORDER BY version"
                        + " LIMIT ? OFFSET ?", this::mapContractVersion, workflowId,
                limit, offset);
        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM wf_versions WHERE workflow_id = ?",
                Integer.class, workflowId);
        return new WorkflowDtos.VersionListOut(items, total == null ? 0 : total,
                limit, offset);
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
                INSERT INTO wf_versions (workflow_id, version, state, nodes, revision,
                created_at) VALUES (?, ?, 'draft', ?, 1, ?)
                """, workflowId, version, json(nodes), now.getEpochSecond());
        jdbc.update("UPDATE wf_defs SET latest_version = ? WHERE workflow_id = ?",
                version, workflowId);
        outbox.enqueue("workflow.version_created", Map.of(
                "workflow_id", workflowId, "version", version));
        return loadVersion(workflowId, version);
    }

    public WorkflowDtos.GraphOut graph(String workflowId, int version) {
        loadDefinition(workflowId);
        VersionRow row = loadVersionRow(workflowId, version);
        return new WorkflowDtos.GraphOut(graphs.load(workflowId, version), row.revision());
    }

    @Transactional
    public WorkflowDtos.GraphOut saveGraph(Actor actor, String workflowId, int version,
                                           WorkflowDtos.GraphIn input, boolean force) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        requireStructural(input.graph());
        loadDefinition(workflowId);
        VersionRow row = loadVersionRow(workflowId, version);
        if ("published".equals(row.state())) {
            throw ApiException.invalid("已发布版本不可修改，请先派生新版本");
        }
        if (!force && input.revision() != row.revision()) {
            throw ApiException.revisionConflict(
                    "版本已被其他人修改，请刷新后重试", row.revision());
        }
        graphs.replace(workflowId, version, input.graph());
        int next = graphs.bumpRevision(workflowId, version);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("workflow_id", workflowId);
        detail.put("version", version);
        detail.put("force", force);
        detail.put("base_revision", row.revision());
        detail.put("revision", next);
        detail.put("node_count", safe(input.graph().nodes()).size());
        detail.put("edge_count", safe(input.graph().edges()).size());
        audit(actor, "workflow.graph_save", "workflow:" + workflowId + ":v" + version, detail);
        return new WorkflowDtos.GraphOut(input.graph(), next);
    }

    public WorkflowDtos.ValidateOut validate(String workflowId, int version,
                                             WorkflowDtos.GraphIn input) {
        loadDefinition(workflowId);
        loadVersionRow(workflowId, version);
        WorkflowDtos.WorkflowGraph graph = input == null
                ? graphs.load(workflowId, version) : input.graph();
        WorkflowGraphValidator.Report report =
                WorkflowGraphValidator.validate(graph.nodes(), graph.edges());
        return new WorkflowDtos.ValidateOut(report.ok(),
                WorkflowGraphValidator.issues(report.errors()),
                WorkflowGraphValidator.issues(report.warnings()), report.stats());
    }

    @Transactional
    public WorkflowDtos.ContractVersionOut cloneVersion(Actor actor, String workflowId,
                                                        int sourceVersion) {
        Authz.require(actor, Authz.WORKFLOW_MODIFY);
        WorkflowDtos.WorkflowOut definition = loadDefinition(workflowId);
        VersionRow source = loadVersionRow(workflowId, sourceVersion);
        int version = definition.latestVersion() + 1;
        Instant now = Instant.now();
        jdbc.update("""
                INSERT INTO wf_versions (workflow_id, version, state, nodes, revision,
                created_at) VALUES (?, ?, 'draft', ?, 1, ?)
                """, workflowId, version, source.nodesJson(), now.getEpochSecond());
        graphs.copy(workflowId, sourceVersion, version);
        jdbc.update("UPDATE wf_defs SET latest_version = ? WHERE workflow_id = ?",
                version, workflowId);
        audit(actor, "workflow.version_cloned", "workflow:" + workflowId + ":v" + version,
                Map.of("workflow_id", workflowId, "source_version", sourceVersion,
                        "version", version));
        outbox.enqueue("workflow.version_created", Map.of(
                "workflow_id", workflowId, "version", version));
        return loadContractVersion(workflowId, version);
    }

    @Transactional
    public WorkflowDtos.ContractVersionOut publish(Actor actor, String workflowId,
                                                   int versionNumber) {
        Authz.require(actor, Authz.WORKFLOW_PUBLISH);
        WorkflowDtos.WorkflowOut definition = loadDefinition(workflowId);
        VersionRow version = loadVersionRow(workflowId, versionNumber);
        if ("published".equals(version.state())) {
            return loadContractVersion(workflowId, versionNumber);
        }
        boolean legacy = !"[]".equals(compact(version.nodesJson())) && version.revision() == 1;
        if (!legacy) {
            WorkflowDtos.WorkflowGraph graph = graphs.load(workflowId, versionNumber);
            WorkflowGraphValidator.Report report =
                    WorkflowGraphValidator.validate(graph.nodes(), graph.edges());
            if (!report.ok()) {
                throw ApiException.publishRejected("流程图校验未通过，不能发布",
                        WorkflowGraphValidator.details(report.errors()));
            }
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
        audit(actor, "workflow.version_published",
                "workflow:" + workflowId + ":v" + versionNumber,
                Map.of("workflow_id", workflowId, "version", versionNumber));
        outbox.enqueue("workflow.version_published", Map.of(
                "workflow_id", workflowId, "version", versionNumber));
        return loadContractVersion(workflowId, versionNumber);
    }

    public WorkflowDtos.VersionOut loadVersion(String workflowId, int version) {
        VersionRow row = loadVersionRow(workflowId, version);
        return new WorkflowDtos.VersionOut(row.workflowId(), row.version(), row.state(),
                parseNodes(row.nodesJson()), row.createdAt(), row.publishedAt());
    }

    public WorkflowDtos.ContractVersionOut loadContractVersion(String workflowId, int version) {
        VersionRow row = loadVersionRow(workflowId, version);
        return new WorkflowDtos.ContractVersionOut(row.workflowId(), row.version(),
                row.state(), row.revision(), row.createdAt(), row.publishedAt());
    }

    private VersionRow loadVersionRow(String workflowId, int version) {
        List<VersionRow> rows = jdbc.query(
                "SELECT * FROM wf_versions WHERE workflow_id = ? AND version = ?",
                this::mapVersionRow, workflowId, version);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("流程版本不存在"));
    }

    public WorkflowDtos.WorkflowOut loadDefinition(String workflowId) {
        List<WorkflowDtos.WorkflowOut> rows = jdbc.query(
                "SELECT * FROM wf_defs WHERE workflow_id = ?", this::mapDefinition, workflowId);
        return rows.stream().findFirst()
                .orElseThrow(() -> ApiException.notFound("流程不存在"));
    }

    private void requireStructural(WorkflowDtos.WorkflowGraph graph) {
        List<WorkflowGraphValidator.Issue> issues = WorkflowGraphValidator.structural(
                graph.nodes(), graph.edges());
        if (!issues.isEmpty()) {
            throw ApiException.invalidGraph("图结构不合法",
                    WorkflowGraphValidator.details(issues));
        }
    }

    private void audit(Actor actor, String action, String resource, Map<String, Object> detail) {
        jdbc.update("INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)"
                        + " VALUES (?, ?, ?, ?, ?)", actor.employeeId(), action, resource,
                json(detail), Instant.now().getEpochSecond());
    }

    private WorkflowDtos.WorkflowOut mapDefinition(java.sql.ResultSet row, int index)
            throws java.sql.SQLException {
        int published = row.getInt("published_version");
        boolean publishedNull = row.wasNull();
        double deletedAt = row.getDouble("deleted_at");
        if (!row.wasNull()) {
            throw ApiException.notFound("流程不存在");
        }
        return new WorkflowDtos.WorkflowOut(
                row.getString("workflow_id"), row.getString("name"),
                row.getInt("latest_version"), publishedNull ? null : published,
                Instant.ofEpochSecond((long) row.getDouble("created_at")), null);
    }

    private VersionRow mapVersionRow(java.sql.ResultSet row, int index)
            throws java.sql.SQLException {
        double publishedAt = row.getDouble("published_at");
        boolean publishedNull = row.wasNull();
        return new VersionRow(row.getString("workflow_id"), row.getInt("version"),
                row.getString("state"), row.getInt("revision"), row.getString("nodes"),
                Instant.ofEpochSecond((long) row.getDouble("created_at")),
                publishedNull ? null : Instant.ofEpochSecond((long) publishedAt));
    }

    private WorkflowDtos.ContractVersionOut mapContractVersion(java.sql.ResultSet row,
                                                                int index)
            throws java.sql.SQLException {
        VersionRow version = mapVersionRow(row, index);
        return new WorkflowDtos.ContractVersionOut(version.workflowId(), version.version(),
                version.state(), version.revision(), version.createdAt(),
                version.publishedAt());
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
            throw ApiException.invalid(label + "不能为空");
        }
        if (name.length() > 64) {
            throw ApiException.invalid(label + "不能超过 64 个字符");
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

    private static String compact(String value) {
        return value == null ? "[]" : value.replaceAll("\\s+", "");
    }

    private static <T> List<T> safe(List<T> value) {
        return value == null ? List.of() : value;
    }

    private record VersionRow(String workflowId, int version, String state, int revision,
                              String nodesJson, Instant createdAt, Instant publishedAt) {
    }
}
