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

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) throws IOException {
        deleteRecursively(DATA_DIR);
        Files.createDirectories(DATA_DIR);
        registry.add("mailbus.data-dir", DATA_DIR::toString);
        registry.add("mailbus.layout-path",
                () -> Path.of("..", "config", "office-layout.json").toAbsolutePath().toString());
        registry.add("mailbus.metrics-manifest-path", () -> Path.of("..", "shared", "config",
                "mailbus", "metrics-manifest.json").toAbsolutePath().toString());
    }

    @Test
    @Order(1)
    void healthIsPublicAndProtectedRoutesRequireToken() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.schema_version").value(12));

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

        mvc.perform(post("/api/identity/invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"account_type\":\"human\",\"capabilities\":[\"bogus\"]}"))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(post("/api/identity/invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"account_type\":\"human\",\"capabilities\":[\"message_send\"]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.invite_code").isNotEmpty());

        mvc.perform(post("/api/identity/staff")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"访客\",\"account_type\":\"human\","
                                + "\"invite_code\":\"nope\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("invite_invalid"));
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
                .andExpect(jsonPath("$").isArray());

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

        mvc.perform(get("/api/org/teams").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("平台组"));

        mvc.perform(get("/api/org/positions").with(auth()))
                .andExpect(status().isOk());

        mvc.perform(get("/api/org/seats").with(auth()))
                .andExpect(status().isOk());

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
                .andExpect(jsonPath("$.rules.length()").value(3));

        mvc.perform(patch("/api/metrics/rules/tasks_failed_today").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"fields\":{\"threshold\":2}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.threshold").value(2.0));

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
                .andExpect(jsonPath("$.alerts").isArray());

        mvc.perform(get("/api/tasks/audit/stats").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_tasks").value(0))
                .andExpect(jsonPath("$.by_reviewer").isMap());

        mvc.perform(get("/api/settings/integrations").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.integrations.length()").value(4));

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

        mvc.perform(post("/api/dev/reload").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reloaded").value(true));
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
                .andExpect(status().isBadRequest())
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

        MvcResult task = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"本周周报\",\"workflow_id\":\"" + workflowId
                                + "\",\"workflow_version\":1}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("draft"))
                .andReturn();
        String taskId = json(task).path("task_id").asText();

        mvc.perform(post("/api/tasks/" + taskId + "/dispatch").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("queued"))
                .andExpect(jsonPath("$.nodes[0].state").value("dispatched"));

        mvc.perform(post("/api/tasks/" + taskId + "/advance").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"node_id\":\"" + nodeId + "\",\"outcome\":\"bogus\"}"))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(post("/api/tasks/" + taskId + "/advance").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"node_id\":\"" + nodeId + "\",\"outcome\":\"done\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes[0].state").value("done"));

        mvc.perform(get("/api/tasks").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].task_id").value(taskId));

        mvc.perform(get("/api/tasks/audit/stats").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_tasks").value(1));

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
        mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"screen_id\":\"s-1\",\"name\":\"大厅大屏\",\"floor_id\":\"f1\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.screen_id").value("s-1"))
                .andExpect(jsonPath("$.online").value(true));

        mvc.perform(post("/api/public/collab/screens")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"缺少编号\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error_code").value("validation_error"));

        mvc.perform(post("/api/public/collab/screens/s-1/heartbeat"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));

        mvc.perform(post("/api/public/collab/screens/missing/heartbeat"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error_code").value("not_found"));

        mvc.perform(get("/api/collab/screens").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].screen_id").value("s-1"))
                .andExpect(jsonPath("$[0].online").value(true));

        mvc.perform(post("/api/collab/screens").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"管理端大屏\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.screen_id").isNotEmpty());

        mvc.perform(post("/api/collab/screens/s-1/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"f2\"}"))
                .andExpect(status().isNoContent());

        mvc.perform(post("/api/collab/screens/s-1/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"\"}"))
                .andExpect(status().isUnprocessableEntity());

        mvc.perform(post("/api/collab/screens/missing/focus").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"floor_id\":\"f2\"}"))
                .andExpect(status().isNotFound());

        mvc.perform(post("/api/public/collab/screens/s-1/leave"))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/collab/screens").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].screen_id").value("s-1"))
                .andExpect(jsonPath("$[0].online").value(false));

        mvc.perform(get("/api/collab/screens"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @Order(8)
    void collabPairsMessagesAndTasks() throws Exception {
        MvcResult invite = mvc.perform(post("/api/identity/invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"account_type\":\"human\",\"capabilities\":[\"message_send\"]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String code = json(invite).path("invite_code").asText();
        MvcResult staff = mvc.perform(post("/api/identity/staff")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"搭档\",\"account_type\":\"human\","
                                + "\"invite_code\":\"" + code + "\"}"))
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
                .andExpect(jsonPath("$").isArray());

        mvc.perform(get("/api/public/collab/tasks").param("owner_id", me))
                .andExpect(status().isOk());
        mvc.perform(get("/api/public/collab/tasks"))
                .andExpect(status().isUnprocessableEntity());

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
