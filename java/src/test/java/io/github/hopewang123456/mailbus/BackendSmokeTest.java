package io.github.hopewang123456.mailbus;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class BackendSmokeTest {

    private static final Path DATA_DIR = Path.of("target", "test-data").toAbsolutePath();
    private static String token = "";

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private io.github.hopewang123456.mailbus.dispatch.OutboxDispatcher dispatcher;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private io.github.hopewang123456.mailbus.ops.OpsService opsService;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) throws IOException {
        deleteRecursively(DATA_DIR);
        Files.createDirectories(DATA_DIR);
        registry.add("mailbus.data-dir", DATA_DIR::toString);
        registry.add("mailbus.layout-path",
                () -> Path.of("..", "config", "office-layout.json").toAbsolutePath().toString());
        registry.add("mailbus.metrics-manifest-path", () -> Path.of("..", "shared", "config",
                "mailbus", "metrics-manifest.json").toAbsolutePath().toString());
        // 测试禁用后台调度：全部拉到 1 小时以上，避免调度线程与 MockMvc 请求抢占同一 SQLite 连接。
        // dispatch 场景由测试显式调 dispatcher.tick() 驱动。
        registry.add("mailbus.dispatch-interval-seconds", () -> 3600);
        registry.add("mailbus.heartbeat-sweep-seconds", () -> 3600);
        registry.add("mailbus.stream-interval-ms", () -> 3600_000);
        registry.add("mailbus.token-encryption-key",
                () -> "test-only-token-encryption-key-32bytes");
    }

    @Test
    @Order(0)
    void sqlitePragmasAreHardened() {
        // 每条新连接都应带 WAL / 外键 / busy_timeout / synchronous=NORMAL
        assertThat(jdbcTemplate.queryForObject("PRAGMA journal_mode", String.class))
                .isEqualToIgnoringCase("wal");
        assertThat(jdbcTemplate.queryForObject("PRAGMA foreign_keys", Integer.class)).isEqualTo(1);
        assertThat(jdbcTemplate.queryForObject("PRAGMA busy_timeout", Integer.class)).isEqualTo(5000);
        // synchronous: 0=OFF, 1=NORMAL, 2=FULL
        assertThat(jdbcTemplate.queryForObject("PRAGMA synchronous", Integer.class)).isEqualTo(1);
    }

    @Test
    @Order(1)
    void healthIsPublicAndProtectedRoutesRequireToken() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.schema_version").value(36));

        mvc.perform(get("/api/openapi.json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths").exists());

        mvc.perform(get("/api/overview"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error_code").value("unauthorized"));

        mvc.perform(get("/api/public/layout"))
                .andExpect(status().isOk());
    }

    @Test
    @Order(2)
    void bootstrapAndSuperAdmin() throws Exception {
        mvc.perform(get("/api/identity/bootstrap"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.completed").value(false));

        MvcResult created = mvc.perform(post("/api/identity/bootstrap/super-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"Root\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.employee.account_type").value("human"))
                .andReturn();
        JsonNode body = objectMapper.readTree(
                created.getResponse().getContentAsString(StandardCharsets.UTF_8));
        token = body.path("token").asText();
        assertThat(token).startsWith("mb_");

        mvc.perform(post("/api/identity/bootstrap/model-config").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"provider\":\"openai\",\"model\":\"gpt-4o\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.completed").value(false));

        mvc.perform(post("/api/identity/bootstrap/team").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"平台组\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("平台组"));

        mvc.perform(get("/api/identity/bootstrap"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.completed").value(true));

        mvc.perform(get("/api/identity/me").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.display_name").value("Root"));

        mvc.perform(get("/api/identity/staff").param("status", "pending").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());

        mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"访客\",\"permissions\":[\"bogus\"]}"))
                .andExpect(status().isUnprocessableEntity());

        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"访客\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.invite_code").isNotEmpty())
                .andReturn();
        String inviteId = json(invite).path("invite_id").asText();
        String inviteCode = json(invite).path("invite_code").asText();
        mvc.perform(post("/api/invites/" + inviteId + "/revoke").with(auth()))
                .andExpect(status().isOk());
        mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode + "\"}"))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.error_code").value("invite_gone"));
    }

    @Test
    @Order(3)
    void readModelsMatchContract() throws Exception {
        mvc.perform(get("/api/overview").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tasks_total").value(0))
                .andExpect(jsonPath("$.metrics").isArray());

        mvc.perform(get("/api/agents").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        MvcResult agent = mvc.perform(post("/api/agents").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"助手\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String agentId = json(agent).path("agent_id").asText();

        mvc.perform(patch("/api/agents/" + agentId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"" + "x".repeat(65) + "\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("validation_error"));

        mvc.perform(patch("/api/agents/" + agentId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":\"bogus\"}"))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/teams").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].name").value("平台组"));

        mvc.perform(get("/api/positions").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        MvcResult team = mvc.perform(post("/api/teams").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"临时组\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String teamId = json(team).path("team_id").asText();
        mvc.perform(delete("/api/teams/" + teamId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(delete("/api/teams/" + teamId).with(auth()))
                .andExpect(status().isNotFound());

        MvcResult position = mvc.perform(post("/api/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"临时岗\",\"capabilities\":[]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String positionId = json(position).path("position_id").asText();
        mvc.perform(delete("/api/positions/" + positionId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(delete("/api/positions/" + positionId).with(auth()))
                .andExpect(status().isNotFound());

        mvc.perform(delete("/api/agents/" + agentId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(delete("/api/agents/" + agentId).with(auth()))
                .andExpect(status().isNotFound());

        MvcResult lockedTeam = mvc.perform(post("/api/teams").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"有人的团队\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String lockedTeamId = json(lockedTeam).path("team_id").asText();
        MvcResult lockedPosition = mvc.perform(post("/api/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"有人的岗位\",\"capabilities\":[]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String lockedPositionId = json(lockedPosition).path("position_id").asText();

        // 归属只能经邀请码带入：邀请决定团队/岗位
        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"在册成员\","
                                + "\"team_id\":\"" + lockedTeamId + "\","
                                + "\"position_id\":\"" + lockedPositionId + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        String inviteCode = json(invite).path("invite_code").asText();
        MvcResult member = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode + "\","
                                + "\"display_name\":\"在册成员\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String memberId = json(member).path("employee").path("employee_id").asText();

        mvc.perform(delete("/api/teams/" + lockedTeamId).with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(delete("/api/positions/" + lockedPositionId).with(auth()))
                .andExpect(status().isConflict());

        mvc.perform(delete("/api/employees/" + memberId).with(auth()))
                .andExpect(status().isNoContent());

        mvc.perform(delete("/api/teams/" + lockedTeamId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(delete("/api/positions/" + lockedPositionId).with(auth()))
                .andExpect(status().isNoContent());

        String seatTeamId = json(mvc.perform(get("/api/teams").with(auth()))
                .andExpect(status().isOk()).andReturn())
                .path("items").path(0).path("team_id").asText();
        mvc.perform(get("/api/teams/" + seatTeamId + "/seats").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        mvc.perform(get("/api/layout").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.floors").isArray());

        mvc.perform(get("/api/log").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());

        mvc.perform(get("/api/log").param("limit", "0").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/identity/staff").param("status", "bogus").with(auth()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("validation_error"))
                .andExpect(jsonPath("$.message_zh").value("请求参数不合法"));

        mvc.perform(get("/api/messages").param("limit", "0").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/messages").param("status", "bogus").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/messages").param("since", "not-a-date").with(auth()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("validation_error"));
    }

    @Test
    @Order(4)
    void metricsAuditAndIntegrations() throws Exception {
        mvc.perform(get("/api/metrics/manifest").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.manifest.metrics").isArray());

        mvc.perform(get("/api/metrics/query").param("metric", "tasks.active")
                        .param("granularity", "1h").param("hours", "24").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.points[0].metric").value("tasks.active"))
                .andExpect(jsonPath("$.series[0].points").isArray());

        mvc.perform(get("/api/metrics/query").param("hours", "0").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/metrics/rules").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(3))
                .andExpect(jsonPath("$.total").value(3));

        mvc.perform(patch("/api/metrics/rules/tasks_failed_today").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"fields\":{\"threshold\":2}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.threshold").value(2.0));
        mvc.perform(get("/api/metrics/rules/tasks_failed_today").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.threshold").value(2.0));
        mvc.perform(get("/api/metrics/rules").param("limit", "1").param("offset", "1")
                        .with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.total").value(3))
                .andExpect(jsonPath("$.limit").value(1))
                .andExpect(jsonPath("$.offset").value(1));

        mvc.perform(get("/api/metrics/layout").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.layout.hidden").isArray());

        mvc.perform(patch("/api/metrics/layout").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"hidden\":[\"bus.unread\",\"bus.unread\",\" \"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.layout.hidden.length()").value(1));

        mvc.perform(get("/api/alerts").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        mvc.perform(get("/api/tasks/audit/stats").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_tasks").value(0))
                .andExpect(jsonPath("$.by_reviewer").isMap());

        mvc.perform(get("/api/settings/integrations").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.integrations.length()").value(4));

        mvc.perform(post("/api/settings/integrations/comfyui/invoke").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"probe\",\"params\":{}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("comfyui"))
                .andExpect(jsonPath("$.action").value("probe"))
                .andExpect(jsonPath("$.result.ok").value(false))
                .andExpect(jsonPath("$.result.name").doesNotExist())
                .andExpect(jsonPath("$.result.action").doesNotExist());

        mvc.perform(post("/api/settings/integrations").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"add_plugin\",\"spec\":\"demo\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.plugins[0]").value("demo"));

        mvc.perform(post("/api/settings/env").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"vars\":{\"AGENTMEMORY_URL\":\"http://memory.local\"}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.groups.agentmemory[0].configured").value(true))
                .andExpect(jsonPath("$.groups.agentmemory[0].value")
                        .value("http://memory.local"));
        mvc.perform(post("/api/settings/env").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"vars\":{\"OPENCLAW_GATEWAY_TOKEN\":\"secret\"}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.groups.openclaw[0].configured").value(true))
                .andExpect(jsonPath("$.groups.openclaw[0].value").value(""));
        mvc.perform(post("/api/settings/env").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"vars\":{\"UNKNOWN\":\"x\"}}"))
                .andExpect(status().isConflict());

        mvc.perform(post("/api/dev/reload").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reloaded").value(false));
    }

    @Test
    @Order(5)
    void workflowTaskAndMessaging() throws Exception {
        MvcResult workflow = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"周报流程\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String workflowId = json(workflow).path("workflow_id").asText();

        mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"未发布\",\"workflow_id\":\"" + workflowId + "\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("version_not_published"));

        MvcResult version = mvc.perform(post("/api/workflows/" + workflowId + "/versions")
                        .with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nodes\":[{\"name\":\"调研\"},{\"name\":\"成稿\"}]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.nodes.length()").value(2))
                .andReturn();
        String nodeId = json(version).path("nodes").get(0).path("node_id").asText();

        mvc.perform(post("/api/workflows/" + workflowId + "/versions/1/publish")
                        .with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("published"));

        mvc.perform(get("/api/workflows/" + workflowId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.published_version").value(1));

        // 旧线性版本没有 wf_nodes，按契约拒绝创建任务
        mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"旧流程任务\",\"workflow_id\":\"" + workflowId + "\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("unprocessable"));

        MvcResult task = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"本周周报\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("running"))
                .andExpect(jsonPath("$.nodes[0].node_id").value("free"))
                .andExpect(jsonPath("$.nodes[0].state").value("running"))
                .andReturn();
        String taskId = json(task).path("task_id").asText();

        MvcResult approval = mvc.perform(post("/api/approvals").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"task_id\":\"" + taskId
                                + "\",\"title\":\"放行\",\"tier\":\"advisory\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String approvalId = json(approval).path("approval_id").asText();
        mvc.perform(delete("/api/approvals/" + approvalId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/approvals/" + approvalId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("withdrawn"));
        mvc.perform(delete("/api/approvals/" + approvalId).with(auth()))
                .andExpect(status().isConflict());

        mvc.perform(get("/api/tasks/summary").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.claimable").value(0))
                .andExpect(jsonPath("$.mine_open").value(1))
                .andExpect(jsonPath("$.approvals").value(0));

        mvc.perform(get("/api/tasks").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].task_id").value(taskId))
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].current_node").value("本周周报"))
                .andExpect(jsonPath("$.items[0].progress_done").value(0))
                .andExpect(jsonPath("$.items[0].progress_total").value(1))
                .andExpect(jsonPath("$.items[0].claimable").value(false));

        mvc.perform(get("/api/public/collab/tasks/" + taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task_id").value(taskId))
                .andExpect(jsonPath("$.title").value("本周周报"))
                .andExpect(jsonPath("$.owner_id").doesNotExist())
                .andExpect(jsonPath("$.created_by").doesNotExist())
                .andExpect(jsonPath("$.workflow_id").doesNotExist())
                .andExpect(jsonPath("$.nodes[0].node_id").doesNotExist());

        mvc.perform(get("/api/public/collab/tasks/" + taskId + "?owner_id=other"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/public/collab/seats/missing-seat/tasks"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/tasks/audit/stats").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_tasks").value(1));

        // 自由任务提交结果后立即完成；重复提交旧 attempt 返回 409
        mvc.perform(post("/api/tasks/" + taskId + "/nodes/free/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"summary\\\":\\\"ok\\\"}\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("done"))
                .andExpect(jsonPath("$.nodes[0].state").value("done"));
        mvc.perform(post("/api/tasks/" + taskId + "/nodes/free/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"summary\\\":\\\"other\\\"}\"}"))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/tasks/" + taskId + "/cancel").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"manual\"}"))
                .andExpect(status().isConflict());

        mvc.perform(post("/api/messages").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"body\":\"hello\",\"channel\":\"bogus\"}"))
                .andExpect(status().isUnprocessableEntity());

        MvcResult message = mvc.perform(post("/api/messages").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"body\":\"hello\",\"channel\":\"file_bus\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String messageId = json(message).path("message_id").asText();

        mvc.perform(get("/api/messages").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].message_id").value(messageId));

        dispatcher.tick();

        mvc.perform(get("/api/messages/" + messageId + "/attempts").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].ok").value(true));

        mvc.perform(get("/api/inbox").with(auth()))
                .andExpect(status().isOk());

        mvc.perform(delete("/api/messages/" + messageId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/messages/" + messageId).with(auth()))
                .andExpect(status().isNotFound());
    }

    @Test
    @Order(6)
    void skillsAndDeleteWorkflow() throws Exception {
        mvc.perform(get("/api/skills/effective").param("target_type", "bogus")
                        .param("target_id", "x").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        Path skillFile = DATA_DIR.resolve("skill").resolve("SKILL.md");
        Files.createDirectories(skillFile.getParent());
        Files.writeString(skillFile, "version: 0.1.0\n");

        mvc.perform(post("/api/skills").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"bad\",\"source_type\":\"http\","
                                + "\"source_uri\":\"ftp://example.invalid\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("skill_source_invalid"));

        MvcResult skill = mvc.perform(post("/api/skills").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"demo\",\"source_type\":\"local\","
                                + "\"source_uri\":\"" + skillFile.toString().replace("\\", "\\\\")
                                + "\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String packageId = json(skill).path("package_id").asText();

        mvc.perform(post("/api/skills/" + packageId + "/refresh").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("0.1.0"));

        mvc.perform(get("/api/skills").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].package_id").value(packageId));

        mvc.perform(post("/api/skills/" + packageId + "/delete").with(auth()))
                .andExpect(status().isNoContent());

        MvcResult disposable = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"待删除\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String disposableId = json(disposable).path("workflow_id").asText();
        mvc.perform(delete("/api/workflows/" + disposableId).with(auth()))
                .andExpect(status().isNoContent());
    }

    @Test
    @Order(7)
    void collabScreenLifecycle() throws Exception {
        // 公开登记：新建时一次性返回明文密钥
        MvcResult registered = mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"大厅大屏\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.screen_id").isNotEmpty())
                .andExpect(jsonPath("$.screen_secret").isNotEmpty())
                .andExpect(jsonPath("$.config_version").value(1))
                .andReturn();
        String screenId = json(registered).path("screen_id").asText();
        String secret = json(registered).path("screen_secret").asText();

        // 库内只存 SHA-256 摘要，不落明文
        String stored = jdbcTemplate.queryForObject(
                "SELECT secret_hash FROM collab_screens WHERE screen_id = ?",
                String.class, screenId);
        assertThat(stored).hasSize(64).isNotEqualTo(secret);
        assertThat(stored).matches("[0-9a-f]{64}");

        // 同编号 + 正确密钥：复用登记，不再回显密钥
        mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"screen_id\":\"" + screenId + "\",\"secret\":\"" + secret
                                + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.screen_id").value(screenId))
                .andExpect(jsonPath("$.screen_secret")
                        .value(org.hamcrest.Matchers.nullValue()));

        // 错误密钥 / 缺少编号：都视为新登记
        MvcResult other = mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"screen_id\":\"" + screenId + "\",\"secret\":\"wrong\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String otherId = json(other).path("screen_id").asText();
        assertThat(otherId).isNotEqualTo(screenId);

        MvcResult anonymous = mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"匿名屏幕\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String anonymousId = json(anonymous).path("screen_id").asText();
        assertThat(anonymousId).isNotEqualTo(screenId);

        // 心跳：错误密钥 403、未知屏幕 404、幂等 200
        mvc.perform(post("/api/public/collab/screens/" + screenId + "/heartbeat")
                        .header("X-Screen-Secret", "wrong"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error_code").value("permission_denied"));
        mvc.perform(post("/api/public/collab/screens/screen_missing/heartbeat")
                        .header("X-Screen-Secret", "whatever"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error_code").value("not_found"));
        mvc.perform(post("/api/public/collab/screens/" + screenId + "/heartbeat")
                        .header("X-Screen-Secret", secret))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));

        // 列表统一分页信封
        mvc.perform(get("/api/collab/screens").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(3))
                .andExpect(jsonPath("$.limit").value(100))
                .andExpect(jsonPath("$.offset").value(0))
                .andExpect(jsonPath("$.items.length()").value(3));

        // 造两个团队与在座员工，验证公开布局按已发布团队过滤
        String teamA = createTeam("大屏团队A");
        String teamB = createTeam("大屏团队B");
        inviteAndSeat("屏A员工", teamA, "f1-bullpen-s1");
        inviteAndSeat("屏B员工", teamB, "f1-bullpen-s2");

        // 草稿：grid 必须绑定团队；保存不递增版本
        mvc.perform(patch("/api/collab/screens/" + screenId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"config\":{\"layout_type\":\"grid\",\"team_id\":\"" + teamA
                                + "\",\"grid\":{\"columns\":4}}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.config_version").value(1))
                .andExpect(jsonPath("$.config.layout_type").value("grid"))
                .andExpect(jsonPath("$.config.team_id").value(teamA));
        mvc.perform(patch("/api/collab/screens/" + screenId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"config\":{\"layout_type\":\"grid\"}}"))
                .andExpect(status().isUnprocessableEntity());

        // 空草稿不可发布
        mvc.perform(post("/api/collab/screens/" + otherId + "/publish").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"expected_config_version\":1}"))
                .andExpect(status().isUnprocessableEntity());

        // 发布 CAS：版本 +1，重复旧版本 409
        mvc.perform(post("/api/collab/screens/" + screenId + "/publish").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"expected_config_version\":1}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.config_version").value(2))
                .andExpect(jsonPath("$.published_at").exists());
        mvc.perform(post("/api/collab/screens/" + screenId + "/publish").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"expected_config_version\":1}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("version_conflict"));

        // 公开配置：只回已发布快照，且不含 team_id
        mvc.perform(get("/api/public/collab/screens/" + screenId + "/config"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.config_version").value(2))
                .andExpect(jsonPath("$.published").value(true))
                .andExpect(jsonPath("$.layout_type").value("grid"))
                .andExpect(jsonPath("$.team_bound").value(true))
                .andExpect(jsonPath("$.play_state").value("playing"))
                .andExpect(jsonPath("$.grid.columns").value(4))
                .andExpect(jsonPath("$.team_id").doesNotExist());
        mvc.perform(get("/api/public/collab/screens/screen_missing/config"))
                .andExpect(status().isNotFound());

        // 公开布局：按已发布团队过滤，且投影不含 team
        JsonNode publicLayout = json(mvc.perform(get("/api/public/layout")
                        .param("screen_id", screenId))
                .andExpect(status().isOk())
                .andReturn());
        JsonNode teamAGent = seatAgent(publicLayout, "f1-bullpen-s1");
        assertThat(teamAGent).isNotNull();
        assertThat(teamAGent.has("team")).isFalse();
        assertThat(seatAgent(publicLayout, "f1-bullpen-s2")).isNull();
        mvc.perform(get("/api/public/layout").param("screen_id", "screen_missing"))
                .andExpect(status().isNotFound());

        // 聚焦：在线 204、缺楼层 422、未知 404
        mvc.perform(post("/api/collab/screens/" + screenId + "/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"f2\"}"))
                .andExpect(status().isNoContent());
        mvc.perform(post("/api/collab/screens/" + screenId + "/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"\"}"))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(post("/api/collab/screens/screen_missing/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"f2\"}"))
                .andExpect(status().isNotFound());

        // 在线屏幕不可删除；离线后聚焦 409、删除 204
        mvc.perform(delete("/api/collab/screens/" + screenId).with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/public/collab/screens/" + screenId + "/leave")
                        .header("X-Screen-Secret", "wrong"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/public/collab/screens/" + screenId + "/leave")
                        .header("X-Screen-Secret", secret))
                .andExpect(status().isNoContent());

        JsonNode listed = json(mvc.perform(get("/api/collab/screens").with(auth()))
                .andExpect(status().isOk()).andReturn());
        JsonNode target = null;
        for (JsonNode item : listed.path("items")) {
            if (screenId.equals(item.path("screen_id").asText())) {
                target = item;
            }
        }
        assertThat(target).isNotNull();
        assertThat(target.path("online").asBoolean()).isFalse();

        mvc.perform(post("/api/collab/screens/" + screenId + "/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"f2\"}"))
                .andExpect(status().isConflict());
        mvc.perform(delete("/api/collab/screens/" + screenId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/public/collab/screens/" + screenId + "/config"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/collab/screens"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @Order(8)
    void collabPairsMessagesAndTasks() throws Exception {
        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"搭档\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andReturn();
        String code = json(invite).path("invite_code").asText();
        MvcResult staff = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + code + "\","
                                + "\"display_name\":\"搭档\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String partnerId = json(staff).path("employee").path("employee_id").asText();
        String me = json(mvc.perform(get("/api/identity/me").with(auth()))
                .andReturn()).path("employee_id").asText();

        mvc.perform(post("/api/collab/pairs").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"partner_id\":\"" + partnerId + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("active"))
                .andExpect(jsonPath("$.initiator_id").value(me));

        MvcResult pair = mvc.perform(get("/api/collab/pairs").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].partner_id").value(partnerId))
                .andReturn();
        String pairId = json(pair).path(0).path("pair_id").asText();

        mvc.perform(post("/api/collab/pairs").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"partner_id\":\"" + partnerId + "\"}"))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/collab/pairs").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"partner_id\":\"" + me + "\"}"))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/collab/pairs").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"partner_id\":\"emp_missing\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(post("/api/collab/messages").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"pair_id\":\"" + pairId + "\",\"body\":\"同步一下\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.pair_id").value(pairId));

        mvc.perform(get("/api/collab/messages").param("pair_id", pairId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].body").value("同步一下"));

        mvc.perform(get("/api/public/collab/messages").param("pair_id", pairId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].pair_id").value(pairId));
        mvc.perform(get("/api/public/collab/messages"))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/tasks").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        mvc.perform(post("/api/collab/pairs/" + pairId + "/end").with(auth()))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/collab/pairs").param("state", "ended").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].state").value("ended"))
                .andExpect(jsonPath("$[0].ended_at").exists());

        mvc.perform(post("/api/collab/messages").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"pair_id\":\"" + pairId + "\",\"body\":\"还能发吗\"}"))
                .andExpect(status().isConflict());

        mvc.perform(post("/api/collab/pairs/pair_missing/end").with(auth()))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/collab/pairs").param("state", "bogus").with(auth()))
                .andExpect(status().isUnprocessableEntity());
    }

    @Test
    @Order(9)
    void orgAdminContractEndpointsWork() throws Exception {
        MvcResult team = mvc.perform(post("/api/teams").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"契约团队\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.team_id").exists())
                .andReturn();
        String teamId = json(team).path("team_id").asText();

        MvcResult position = mvc.perform(post("/api/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"契约岗位\",\"capabilities\":[\"analysis\"]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.role_ids").isArray())
                .andReturn();
        String positionId = json(position).path("position_id").asText();

        MvcResult role = mvc.perform(post("/api/roles").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"契约角色\",\"capabilities\":[\"analysis\"]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.enabled").value(true))
                .andReturn();
        String roleId = json(role).path("role_id").asText();

        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/roles/" + roleId + "/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"ids\":[\"" + positionId + "\"]}"))
                .andExpect(status().isOk());
        mvc.perform(delete("/api/roles/" + roleId).with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/roles/" + roleId + "/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"ids\":[]}"))
                .andExpect(status().isOk());

        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"契约员工\",\"team_id\":\"" + teamId
                                + "\",\"position_id\":\"" + positionId
                                + "\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.invite_code").exists())
                .andExpect(jsonPath("$.permissions[0]").value("message_send"))
                .andReturn();
        String inviteId = json(invite).path("invite_id").asText();
        String inviteCode = json(invite).path("invite_code").asText();

        MvcResult accepted = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode
                                + "\",\"display_name\":\"契约员工\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.employee.status").value("active"))
                .andExpect(jsonPath("$.employee.permissions[0]").value("message_send"))
                .andExpect(jsonPath("$.token").exists())
                .andReturn();
        String employeeId = json(accepted).path("employee").path("employee_id").asText();
        String employeeToken = json(accepted).path("token").asText();

        mvc.perform(get("/api/employees/" + employeeId + "/capabilities").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.capabilities[0]").value("analysis"));
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/employees/" + employeeId + "/permissions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"permissions\":[\"message_send\",\"log_read\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.permissions[1]").value("message_send"));
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/employees/" + employeeId + "/roles").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"role_ids\":[\"" + roleId + "\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role_ids[0]").value(roleId));
        mvc.perform(get("/api/employees").param("type", "human").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());
        mvc.perform(get("/api/options/positions").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());

        mvc.perform(delete("/api/employees/" + employeeId).with(authToken(employeeToken)))
                .andExpect(status().isForbidden());
        mvc.perform(delete("/api/employees/" + employeeId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/employees/" + employeeId).with(auth()))
                .andExpect(status().isNotFound());

        mvc.perform(post("/api/invites/" + inviteId + "/revoke").with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode + "\"}"))
                .andExpect(status().isGone());
        mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"inv_missing\"}"))
                .andExpect(status().isNotFound());

        MvcResult revocable = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"待撤销\",\"team_id\":\"" + teamId
                                + "\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andReturn();
        String revocableId = json(revocable).path("invite_id").asText();
        String revocableCode = json(revocable).path("invite_code").asText();
        mvc.perform(post("/api/invites/" + revocableId + "/revoke").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revoked_at").exists())
                .andExpect(jsonPath("$.invite_code").value(org.hamcrest.Matchers.nullValue()));
        mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + revocableCode + "\"}"))
                .andExpect(status().isGone());

        MvcResult resendSource = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"待重发\",\"team_id\":\"" + teamId
                                + "\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andReturn();
        String resendId = json(resendSource).path("invite_id").asText();
        mvc.perform(post("/api/invites/" + resendId + "/resend").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.invite_code").exists())
                .andExpect(jsonPath("$.invite_id").value(org.hamcrest.Matchers.not(resendId)));

        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/seats/f1-bullpen-s1/assign").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"team_id\":\"" + teamId + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.team_id").value(teamId));
        mvc.perform(delete("/api/teams/" + teamId).with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/seats/f1-bullpen-s1/assign").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"team_id\":null}"))
                .andExpect(status().isOk());
        mvc.perform(delete("/api/teams/" + teamId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(delete("/api/positions/" + positionId).with(auth()))
                .andExpect(status().isNoContent());
    }

    @Test
    @Order(10)
    void workflowGraphContractParity() throws Exception {
        String start = "{\"node_id\":\"start\",\"name\":\"开始\",\"node_type\":\"start\",\"seq\":0}";
        String agent = "{\"node_id\":\"agent_a\",\"name\":\"执行\",\"node_type\":\"agent\","
                + "\"position_id\":\"pos_demo\",\"seq\":1}";
        String fin = "{\"node_id\":\"final\",\"name\":\"终验\",\"node_type\":\"final_approval\","
                + "\"position_id\":\"pos_final\",\"seq\":2}";
        String toAgent = "{\"from_node_id\":\"start\",\"to_node_id\":\"agent_a\"}";
        String toFinal = "{\"from_node_id\":\"agent_a\",\"to_node_id\":\"final\"}";

        MvcResult created = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Graph流程\",\"graph\":" + workflowGraph(
                                start + "," + agent + "," + fin, toAgent + "," + toFinal)
                                + "}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.latest_version").value(1))
                .andReturn();
        String workflowId = json(created).path("workflow_id").asText();

        mvc.perform(get("/api/workflows").param("limit", "10").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.total").isNumber());

        mvc.perform(get("/api/workflows/" + workflowId + "/versions").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].revision").value(1))
                .andExpect(jsonPath("$.items[0].nodes").doesNotExist());

        mvc.perform(get("/api/workflows/" + workflowId + "/versions/1/graph").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revision").value(1))
                .andExpect(jsonPath("$.graph.nodes.length()").value(3))
                .andExpect(jsonPath("$.graph.edges.length()").value(2));

        // 结构错误：重复节点 ID → 400 + errors 清单
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(1, start + "," + start, "")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("invalid_graph"))
                .andExpect(jsonPath("$.errors").isArray());

        // 正常保存：revision +1
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(1, start + "," + agent + "," + fin,
                                toAgent + "," + toFinal)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revision").value(2));

        // 过期 revision → 409 + 服务端 revision
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(1, start + "," + agent + "," + fin,
                                toAgent + "," + toFinal)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("revision_conflict"))
                .andExpect(jsonPath("$.revision").value(2));

        // force 覆盖：跳过比较但仍 +1
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph")
                        .param("force", "true").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(1, start + "," + agent + "," + fin,
                                toAgent + "," + toFinal)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revision").value(3));

        mvc.perform(post("/api/workflows/" + workflowId + "/versions/1/validate").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));

        // 发布阻断：缺少终验节点 → 422 + errors
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph")
                        .param("force", "true").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(3, start + "," + agent, toAgent)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revision").value(4));

        mvc.perform(post("/api/workflows/" + workflowId + "/versions/1/publish").with(auth()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("publish_invalid"))
                .andExpect(jsonPath("$.errors").isArray());

        // 恢复完整图后发布成功
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph")
                        .param("force", "true").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(4, start + "," + agent + "," + fin,
                                toAgent + "," + toFinal)))
                .andExpect(status().isOk());
        mvc.perform(post("/api/workflows/" + workflowId + "/versions/1/publish").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("published"));

        // 已发布版本不可再改
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .put("/api/workflows/" + workflowId + "/versions/1/graph").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(graphBody(5, start + "," + agent + "," + fin,
                                toAgent + "," + toFinal)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("invalid_state"));

        // 派生新版：复制 Graph，revision 重置为 1
        mvc.perform(post("/api/workflows/" + workflowId + "/versions/1/clone").with(auth()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.version").value(2))
                .andExpect(jsonPath("$.state").value("draft"))
                .andExpect(jsonPath("$.revision").value(1));

        mvc.perform(get("/api/workflows/" + workflowId + "/versions/2/graph").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.graph.nodes.length()").value(3))
                .andExpect(jsonPath("$.graph.edges.length()").value(2));

        // 软删除：列表与详情都不再可见
        mvc.perform(delete("/api/workflows/" + workflowId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/workflows/" + workflowId).with(auth()))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/workflows").param("limit", "100").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[?(@.workflow_id == '" + workflowId + "')]")
                        .isEmpty());
    }

    @Test
    @Order(11)
    void taskDomainEngineParity() throws Exception {
        String start = "{\"node_id\":\"start\",\"name\":\"开始\",\"node_type\":\"start\",\"seq\":0}";
        String human = "{\"node_id\":\"human_review\",\"name\":\"人工审核\","
                + "\"node_type\":\"human\",\"position_id\":\"pos_demo\",\"seq\":1}";
        String fin = "{\"node_id\":\"final\",\"name\":\"终验\",\"node_type\":\"final_approval\","
                + "\"position_id\":\"pos_final\",\"seq\":2}";
        String toHuman = "{\"from_node_id\":\"start\",\"to_node_id\":\"human_review\"}";
        String toFinal = "{\"from_node_id\":\"human_review\",\"to_node_id\":\"final\"}";
        MvcResult flow = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"人工终验流程\",\"graph\":" + workflowGraph(
                                start + "," + human + "," + fin, toHuman + "," + toFinal)
                                + "}"))
                .andExpect(status().isCreated())
                .andReturn();
        String flowId = json(flow).path("workflow_id").asText();
        mvc.perform(post("/api/workflows/" + flowId + "/versions/1/publish").with(auth()))
                .andExpect(status().isOk());

        // 认领 → 提交 → 终验通过
        MvcResult created = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"人工终验任务\",\"workflow_id\":\"" + flowId + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("running"))
                .andReturn();
        String taskId = json(created).path("task_id").asText();

        MvcResult detail = mvc.perform(get("/api/tasks/" + taskId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[1].state").value("running"))
                .andExpect(jsonPath("$.nodes[1].runs[0].state").value("pending"))
                .andExpect(jsonPath("$.nodes[1].runs[0].assigned_employee_id").doesNotExist())
                .andReturn();
        assertThat(json(detail).path("nodes").get(1).path("runs").get(0)
                .path("attempt_no").asInt()).isEqualTo(1);

        mvc.perform(post("/api/tasks/" + taskId + "/nodes/human_review/claim").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[1].state").value("running"));
        mvc.perform(post("/api/tasks/" + taskId + "/nodes/human_review/claim").with(auth()))
                .andExpect(status().isConflict());

        mvc.perform(post("/api/tasks/" + taskId + "/nodes/human_review/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"approved\\\":true}\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[1].state").value("done"))
                .andExpect(jsonPath("$.state").value("running"));

        MvcResult approvals = mvc.perform(get("/api/approvals")
                        .param("state", "pending").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray())
                .andReturn();
        String finalApprovalId = null;
        for (JsonNode item : json(approvals).path("items")) {
            if (taskId.equals(item.path("task_id").asText())) {
                finalApprovalId = item.path("approval_id").asText();
                assertThat(item.path("node_id").asText()).isEqualTo("final");
            }
        }
        assertThat(finalApprovalId).isNotNull();

        mvc.perform(post("/api/approvals/" + finalApprovalId + "/resolve").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"rejected\"}"))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(post("/api/approvals/" + finalApprovalId + "/resolve").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"approved\",\"comment\":\"通过\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("approved"));
        mvc.perform(get("/api/tasks/" + taskId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("done"))
                .andExpect(jsonPath("$.nodes[2].state").value("done"));
        mvc.perform(post("/api/approvals/" + finalApprovalId + "/resolve").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"approved\",\"comment\":\"重复\"}"))
                .andExpect(status().isConflict());

        // 失败升级转人工：节点阻塞、任务阻塞
        MvcResult failing = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"失败转人工\",\"workflow_id\":\"" + flowId + "\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String failingId = json(failing).path("task_id").asText();
        mvc.perform(post("/api/tasks/" + failingId + "/nodes/human_review/claim").with(auth()))
                .andExpect(status().isOk());
        mvc.perform(post("/api/tasks/" + failingId + "/nodes/human_review/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"status\\\":\\\"failed\\\"}\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("blocked"))
                .andExpect(jsonPath("$.nodes[1].state").value("blocked"))
                .andExpect(jsonPath("$.nodes[1].runs[1].state").value("pending"));

        // 扇出缺片 → rerun-join 强制汇聚并写审计
        String fanHuman = "{\"node_id\":\"fan_review\",\"name\":\"并行审核\","
                + "\"node_type\":\"human\",\"position_id\":\"pos_demo\",\"seq\":1,"
                + "\"config\":{\"fanout\":2}}";
        String join = "{\"node_id\":\"join\",\"name\":\"汇聚\",\"node_type\":\"parallel_join\","
                + "\"seq\":2}";
        String fanFin = "{\"node_id\":\"final\",\"name\":\"终验\",\"node_type\":\"final_approval\","
                + "\"position_id\":\"pos_final\",\"seq\":3}";
        String edges = "{\"from_node_id\":\"start\",\"to_node_id\":\"fan_review\"},"
                + "{\"from_node_id\":\"fan_review\",\"to_node_id\":\"join\"},"
                + "{\"from_node_id\":\"join\",\"to_node_id\":\"final\"}";
        MvcResult fanFlow = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"并行汇聚流程\",\"graph\":" + workflowGraph(
                                start + "," + fanHuman + "," + join + "," + fanFin, edges)
                                + "}"))
                .andExpect(status().isCreated())
                .andReturn();
        String fanFlowId = json(fanFlow).path("workflow_id").asText();
        mvc.perform(post("/api/workflows/" + fanFlowId + "/versions/1/publish").with(auth()))
                .andExpect(status().isOk());
        MvcResult fanTask = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"并行任务\",\"workflow_id\":\"" + fanFlowId + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.nodes[1].runs.length()").value(2))
                .andReturn();
        String fanTaskId = json(fanTask).path("task_id").asText();
        mvc.perform(post("/api/tasks/" + fanTaskId + "/nodes/fan_review/claim").with(auth()))
                .andExpect(status().isOk());
        mvc.perform(post("/api/tasks/" + fanTaskId + "/nodes/fan_review/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"ok\\\":1}\"}"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/tasks/" + fanTaskId + "/nodes/fan_review/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"{\\\"status\\\":\\\"failed\\\"}\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[1].state").value("failed"));
        mvc.perform(post("/api/tasks/" + fanTaskId + "/nodes/join/rerun-join").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"fanout_group\":\"manual-fix\",\"scope\":\"join\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[2].state").value("done"))
                .andExpect(jsonPath("$.nodes[3].state").value("pending"));
        Integer audits = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM ops_audit_log"
                + " WHERE action = 'task.join_rerun' AND resource = ?", Integer.class,
                "task:" + fanTaskId);
        assertThat(audits).isEqualTo(1);

        // 取消原因校验
        MvcResult freeTask = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"取消测试\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String freeId = json(freeTask).path("task_id").asText();
        mvc.perform(post("/api/tasks/" + freeId + "/cancel").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"bogus\"}"))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(post("/api/tasks/" + freeId + "/cancel").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"manual\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("cancelled"))
                .andExpect(jsonPath("$.termination_reason").value("manual"));
        mvc.perform(post("/api/tasks/" + freeId + "/cancel").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"manual\"}"))
                .andExpect(status().isConflict());
    }

    @Test
    @Order(12)
    void agentA2ADomainParity() throws Exception {
        // 非法 token 直接 401
        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"type\":\"heartbeat\"}")
                        .header("Authorization", "Bearer not-a-real-token"))
                .andExpect(status().isUnauthorized());

        MvcResult position = mvc.perform(post("/api/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Agent 岗\",\"capabilities\":[]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String positionId = json(position).path("position_id").asText();

        // metadata 地址必须被 SSRF 防护拒绝
        MvcResult badInvite = mvc.perform(post("/api/agent-invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"employee_name\":\"坏 Agent\",\"position_id\":\""
                                + positionId + "\",\"capabilities\":[\"ops\"],"
                                + "\"permissions\":[\"message_send\",\"result_submit\"]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String badCode = json(badInvite).path("invite_code").asText();
        mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + badCode + "\",\"name\":\"坏 Agent\","
                                + "\"endpoint\":\"http://169.254.169.254/latest/meta-data\"}"))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(post("/api/agent-invites/"
                        + json(badInvite).path("invite_id").asText() + "/revoke").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.revoked_at").isNotEmpty());
        mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + badCode + "\",\"name\":\"已撤销\"}"))
                .andExpect(status().isGone());
        mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"mbreg_missing\",\"name\":\"不存在\"}"))
                .andExpect(status().isNotFound());

        MvcResult invite = mvc.perform(post("/api/agent-invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"employee_name\":\"执行 Agent\",\"position_id\":\""
                                + positionId + "\",\"capabilities\":[\"ops\"],"
                                + "\"permissions\":[\"message_send\",\"result_submit\"]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.invite_code").isNotEmpty())
                .andReturn();
        String inviteCode = json(invite).path("invite_code").asText();

        MvcResult registered = mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode + "\","
                                + "\"name\":\"执行 Agent\","
                                + "\"endpoint\":\"http://127.0.0.1:7890/a2a\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.endpoint_review_status").value("pending"))
                .andReturn();
        JsonNode registration = json(registered);
        String agentId = registration.path("agent_id").asText();
        String employeeId = registration.path("employee_id").asText();
        String agentToken = registration.path("token").asText();
        assertThat(agentToken).startsWith("mbk");

        mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + inviteCode
                                + "\",\"name\":\"重复注册\"}"))
                .andExpect(status().isConflict());
        MvcResult invitePage = mvc.perform(get("/api/agent-invites").with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        String invitePageBody = invitePage.getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(invitePageBody).doesNotContain(inviteCode);
        for (JsonNode item : json(invitePage).path("items")) {
            if (item.path("invite_id").asText().equals(json(invite).path("invite_id").asText())) {
                assertThat(item.path("expires_at").isNull()).isTrue();
            }
        }

        // 明文绝不落库：只存 AES-GCM 密文 + 反查摘要
        String storedToken = jdbcTemplate.queryForObject(
                "SELECT endpoint_token FROM agents WHERE agent_id = ?", String.class, agentId);
        String storedDigest = jdbcTemplate.queryForObject(
                "SELECT endpoint_token_lookup_hash FROM agents WHERE agent_id = ?",
                String.class, agentId);
        assertThat(storedToken).startsWith("enc:").isNotEqualTo(agentToken);
        assertThat(storedDigest).isNotBlank();

        MvcResult listed = mvc.perform(get("/api/agents").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].agent_id").value(agentId))
                .andExpect(jsonPath("$.items[0].endpoint_review_status").value("pending"))
                .andExpect(jsonPath("$.items[0].endpoint")
                        .value(org.hamcrest.Matchers.nullValue()))
                .andExpect(jsonPath("$.items[0].pending_endpoint")
                        .value("http://127.0.0.1:7890/a2a"))
                .andReturn();
        assertThat(listed.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .doesNotContain(agentToken);

        String start = "{\"node_id\":\"start\",\"name\":\"开始\",\"node_type\":\"start\","
                + "\"seq\":0}";
        String work = "{\"node_id\":\"work\",\"name\":\"执行\",\"node_type\":\"agent\","
                + "\"position_id\":\"" + positionId + "\",\"seq\":1}";
        String fin = "{\"node_id\":\"final\",\"name\":\"终验\","
                + "\"node_type\":\"final_approval\",\"position_id\":\"" + positionId
                + "\",\"seq\":2}";
        String edges = "{\"from_node_id\":\"start\",\"to_node_id\":\"work\"},"
                + "{\"from_node_id\":\"work\",\"to_node_id\":\"final\"}";
        MvcResult flow = mvc.perform(post("/api/workflows").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Agent 流\",\"graph\":" + workflowGraph(
                                start + "," + work + "," + fin, edges) + "}"))
                .andExpect(status().isCreated())
                .andReturn();
        String flowId = json(flow).path("workflow_id").asText();
        mvc.perform(post("/api/workflows/" + flowId + "/versions/1/publish").with(auth()))
                .andExpect(status().isOk());

        // endpoint 待审批：绝不派单
        mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Agent 任务\",\"workflow_id\":\"" + flowId + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.nodes[1].runs.length()").value(0));

        mvc.perform(post("/api/agents/" + agentId + "/endpoint/approve").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.endpoint_review_status").value("approved"))
                .andExpect(jsonPath("$.endpoint").value("http://127.0.0.1:7890/a2a"));

        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + agentToken)
                        .content("{\"type\":\"heartbeat\","
                                + "\"endpoint\":\"http://127.0.0.1:7890/a2a\"}"))
                .andExpect(status().isCreated());

        MvcResult started = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Agent 任务 2\",\"workflow_id\":\"" + flowId + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.nodes[1].runs.length()").value(1))
                .andExpect(jsonPath("$.nodes[1].runs[0].assigned_employee_id")
                        .value(employeeId))
                .andReturn();
        JsonNode run = json(started).path("nodes").get(1).path("runs").get(0);
        String runId = run.path("run_id").asText();
        int attemptNo = run.path("attempt_no").asInt();

        String resultBody = "{\"type\":\"result\",\"run_id\":\"" + runId
                + "\",\"attempt_no\":" + attemptNo
                + ",\"status\":\"completed\",\"output\":\"done\"}";
        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + agentToken)
                        .content(resultBody))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.duplicate").value(false));

        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + agentToken)
                        .content(resultBody))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.duplicate").value(true));

        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + agentToken)
                        .content("{\"type\":\"result\",\"run_id\":\"" + runId
                                + "\",\"attempt_no\":" + (attemptNo + 1)
                                + ",\"status\":\"completed\",\"output\":\"done\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error_code").value("stale_run"));

        MvcResult rotated = mvc.perform(post("/api/agents/" + agentId + "/rotate-token")
                        .with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        String newToken = json(rotated).path("token").asText();
        assertThat(newToken).isNotEqualTo(agentToken);
        // 轮转宽限期内新旧 token 均可心跳
        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + agentToken)
                        .content("{\"type\":\"heartbeat\"}"))
                .andExpect(status().isCreated());
        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + newToken)
                        .content("{\"type\":\"heartbeat\"}"))
                .andExpect(status().isCreated());

        mvc.perform(post("/api/agents/" + agentId + "/revoke-token").with(auth()))
                .andExpect(status().isOk());
        mvc.perform(post("/api/a2a/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + newToken)
                        .content("{\"type\":\"heartbeat\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/agents").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].online").value(false));
    }

    private static String graphBody(int revision, String nodes, String edges) {
        return "{\"revision\":" + revision + ",\"graph\":" + workflowGraph(nodes, edges) + "}";
    }

    private static String workflowGraph(String nodes, String edges) {
        return "{\"nodes\":[" + nodes + "],\"edges\":[" + edges + "]}";
    }

    @Test
    @Order(13)
    void metricsReportsAndAuditParity() throws Exception {
        int taskTotal = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM task_tasks", Integer.class);
        MvcResult overviewResult = mvc.perform(get("/api/metrics/overview").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totals.total").value(taskTotal))
                .andExpect(jsonPath("$.cards").isArray())
                .andReturn();
        JsonNode cards = json(overviewResult).path("cards");
        assertThat(cards).anyMatch(card -> card.path("metric").asText().equals("tasks.total")
                && card.path("value").asInt() == taskTotal);
        assertThat(cards).anyMatch(card -> card.path("metric").asText().equals("tasks.completion_rate")
                && card.path("unit").asText().equals("percent"));
        assertThat(cards).anyMatch(card -> card.path("metric").asText().equals("agents.online"));
        assertThat(cards).anyMatch(card -> card.path("metric").asText().equals("tasks.backlog"));

        MvcResult trendResult = mvc.perform(get("/api/metrics/trend")
                        .param("bucket", "day").with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode trendSeries = json(trendResult).path("series");
        assertThat(trendSeries).anyMatch(series ->
                series.path("metric").asText().equals("tasks.created"));
        assertThat(trendSeries).anyMatch(series ->
                series.path("metric").asText().equals("tasks.completed"));
        for (JsonNode series : trendSeries) {
            if (series.path("metric").asText().equals("tasks.created")) {
                int created = 0;
                for (JsonNode point : series.path("points")) {
                    created += point.path("value").asInt();
                }
                assertThat(created).isEqualTo(taskTotal);
            }
        }
        mvc.perform(get("/api/metrics/breakdown").param("metric", "agent_load").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.metric").value("agent_load"))
                .andExpect(jsonPath("$.items").isArray())
                .andExpect(jsonPath("$.extra").isMap());
        mvc.perform(get("/api/metrics/breakdown").param("metric", "nope").with(auth()))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(get("/api/metrics/trend").param("metric", "nope").with(auth()))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(get("/api/metrics/trend").param("bucket", "week").with(auth()))
                .andExpect(status().isUnprocessableEntity());
        mvc.perform(get("/api/metrics/overview").param("from", "2999-01-01").with(auth()))
                .andExpect(status().isUnprocessableEntity());

        MvcResult exported = mvc.perform(get("/api/metrics/export").with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(exported.getResponse().getContentType()).startsWith("text/csv");
        assertThat(exported.getResponse().getHeader("Content-Disposition")).contains("attachment");
        String exportBody = exported.getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(exportBody).contains("section").contains("tasks.total");

        MvcResult visitorInvite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"报表访客\"}"))
                .andExpect(status().isOk())
                .andReturn();
        MvcResult activated = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\""
                                + json(visitorInvite).path("invite_code").asText()
                                + "\",\"display_name\":\"报表访客\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String visitorToken = json(activated).path("token").asText();
        mvc.perform(get("/api/metrics/overview").with(authToken(visitorToken)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totals.total").value(0));
        MvcResult scopedExport = mvc.perform(get("/api/metrics/export").with(authToken(visitorToken)))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(scopedExport.getResponse().getContentAsString(StandardCharsets.UTF_8)
                .lines().toList())
                .anyMatch(line -> line.contains("tasks.total") && line.endsWith(",0,count"));

        jdbcTemplate.update("""
                INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, "emp_root", "test.change", "thing:1",
                "{\"before\":{\"a\":1,\"b\":1},\"after\":{\"a\":2,\"c\":3},\"note\":\"x\"}",
                System.currentTimeMillis() / 1000.0);
        MvcResult auditResult = mvc.perform(get("/api/audit").param("action", "test.change")
                        .with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].detail.note").value("x"))
                .andExpect(jsonPath("$.items[0].detail.diff").doesNotExist())
                .andReturn();
        JsonNode audit = json(auditResult).path("items").get(0);
        MvcResult detailResult = mvc.perform(get("/api/audit/" + audit.path("audit_id").asLong())
                        .with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode diff = json(detailResult).path("detail").path("diff");
        assertThat(diff).anyMatch(item -> item.path("field").asText().equals("a")
                && item.path("before").asInt() == 1 && item.path("after").asInt() == 2);
        assertThat(diff).anyMatch(item -> item.path("field").asText().equals("b")
                && item.path("after").isNull());
        assertThat(diff).anyMatch(item -> item.path("field").asText().equals("c")
                && item.path("before").isNull());
        mvc.perform(get("/api/audit").param("action", "test.change")
                        .param("actor", "nobody").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0));
        MvcResult auditCsv = mvc.perform(get("/api/audit").param("action", "test.change")
                        .param("format", "csv").with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(auditCsv.getResponse().getContentType()).startsWith("text/csv");
        assertThat(auditCsv.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .contains("audit_id").contains("test.change");
        mvc.perform(get("/api/audit/999999").with(auth()))
                .andExpect(status().isNotFound());
    }

    @Test
    @Order(14)
    void opsAlertLifecycleAndCooldownParity() throws Exception {
        MvcResult ruleResult = mvc.perform(post("/api/alert-rules").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Agent 离线\",\"alert_type\":\"agent_offline\","
                                + "\"threshold\":60,\"channel\":\"inapp\","
                                + "\"silence_seconds\":600}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.enabled").value(true))
                .andExpect(jsonPath("$.threshold").value(60.0))
                .andReturn();
        String ruleId = json(ruleResult).path("rule_id").asText();
        mvc.perform(get("/api/alert-rules").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].rule_id").value(ruleId));

        double now = System.currentTimeMillis() / 1000.0;
        jdbcTemplate.update("UPDATE agents SET last_seen_at = ?", now);
        String agentId = jdbcTemplate.queryForObject(
                "SELECT agent_id FROM agents ORDER BY created_at DESC LIMIT 1", String.class);
        jdbcTemplate.update("UPDATE agents SET last_seen_at = ? WHERE agent_id = ?",
                now - 3600, agentId);
        assertThat(opsService.evaluate()).isEqualTo(1);

        MvcResult firingResult = mvc.perform(get("/api/alerts").param("state", "firing")
                        .with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].type").value("agent_offline"))
                .andExpect(jsonPath("$.items[0].severity").value("warn"))
                .andExpect(jsonPath("$.items[0].resource_id").value(agentId))
                .andExpect(jsonPath("$.items[0].status").value("firing"))
                .andReturn();
        String alertId = json(firingResult).path("items").get(0).path("alert_id").asText();
        mvc.perform(get("/api/audit").param("action", "alert.notified").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].detail.ok").value(true))
                .andExpect(jsonPath("$.items[0].detail.attempts").value(1));

        mvc.perform(post("/api/alerts/" + alertId + "/ack").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("acked"))
                .andExpect(jsonPath("$.acked_by").isNotEmpty());
        mvc.perform(post("/api/alerts/" + alertId + "/ack").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("acked"));
        assertThat(opsService.evaluate()).isEqualTo(0);
        mvc.perform(get("/api/alerts").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));
        mvc.perform(get("/api/audit").param("action", "alert.notified").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));

        jdbcTemplate.update("UPDATE agents SET last_seen_at = ? WHERE agent_id = ?",
                System.currentTimeMillis() / 1000.0, agentId);
        assertThat(opsService.evaluate()).isEqualTo(0);
        mvc.perform(get("/api/alerts").param("state", "resolved").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].resolved_at").isNotEmpty());
        mvc.perform(get("/api/audit").param("action", "alert.notified").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));
        mvc.perform(post("/api/alerts/" + alertId + "/ack").with(auth()))
                .andExpect(status().isConflict());

        jdbcTemplate.update("UPDATE agents SET last_seen_at = ? WHERE agent_id = ?",
                System.currentTimeMillis() / 1000.0 - 3600, agentId);
        assertThat(opsService.evaluate()).isEqualTo(1);
        mvc.perform(get("/api/alerts").param("state", "firing").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));
        mvc.perform(get("/api/audit").param("action", "alert.notified").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));
        mvc.perform(post("/api/alert-rules/" + ruleId + "/test").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));
        mvc.perform(patch("/api/alert-rules/" + ruleId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":false}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false));
        mvc.perform(delete("/api/alert-rules/" + ruleId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/alert-rules").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0));

        mvc.perform(post("/api/alert-rules").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"未知\",\"alert_type\":\"nope\","
                                + "\"channel\":\"inapp\"}"))
                .andExpect(status().isUnprocessableEntity());
        MvcResult webhook = mvc.perform(post("/api/alert-rules").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Webhook 失败\",\"alert_type\":\"agent_offline\","
                                + "\"threshold\":60,\"channel\":\"webhook\","
                                + "\"target\":\"http://127.0.0.1:9/unreachable\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String webhookId = json(webhook).path("rule_id").asText();
        mvc.perform(post("/api/alert-rules/" + webhookId + "/test").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(false))
                .andExpect(jsonPath("$.message_zh").value(org.hamcrest.Matchers.containsString("失败")));
        mvc.perform(get("/api/audit").param("action", "alert_rule.tested")
                        .param("resource", webhookId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].detail.ok").value(false))
                .andExpect(jsonPath("$.items[0].detail.attempts").value(3));
        mvc.perform(patch("/api/alert-rules/alr_missing").with(auth())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"name\":\"x\"}"))
                .andExpect(status().isNotFound());
        mvc.perform(delete("/api/alert-rules/alr_missing").with(auth()))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/alerts/alert_missing/ack").with(auth()))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/alerts"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/audit"))
                .andExpect(status().isUnauthorized());
    }

    private String createTeam(String name) throws Exception {
        MvcResult created = mvc.perform(post("/api/teams").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"" + name + "\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        return json(created).path("team_id").asText();
    }

    private String inviteAndSeat(String name, String teamId, String seatId) throws Exception {
        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"" + name + "\",\"team_id\":\"" + teamId
                                + "\",\"permissions\":[\"message_send\"]}"))
                .andExpect(status().isOk())
                .andReturn();
        String code = json(invite).path("invite_code").asText();
        MvcResult accepted = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + code + "\",\"display_name\":\"" + name
                                + "\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        String employeeId = json(accepted).path("employee").path("employee_id").asText();
        mvc.perform(patch("/api/employees/" + employeeId).with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"seat_id\":\"" + seatId + "\"}"))
                .andExpect(status().isOk());
        return employeeId;
    }

    private static JsonNode seatAgent(JsonNode layout, String seatId) {
        for (JsonNode floor : layout.path("floors")) {
            for (JsonNode room : floor.path("rooms")) {
                for (JsonNode seat : room.path("seats")) {
                    if (seatId.equals(seat.path("seat_id").asText())) {
                        JsonNode agent = seat.path("agent");
                        return agent.isNull() ? null : agent;
                    }
                }
            }
        }
        return null;
    }

    private org.springframework.test.web.servlet.request.RequestPostProcessor authToken(
            String tokenValue) {
        return request -> {
            request.addHeader("Authorization", "Bearer " + tokenValue);
            return request;
        };
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private org.springframework.test.web.servlet.request.RequestPostProcessor auth() {
        return request -> {
            request.addHeader("Authorization", "Bearer " + token);
            return request;
        };
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var walk = Files.walk(root)) {
            walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                    // 清理失败不阻断测试
                }
            });
        }
    }
}
