package io.github.hopewang123456.mailbus;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ContractStubsTest {

    private static final Path DATA_DIR = Path.of("target", "test-contract-stubs").toAbsolutePath();

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper objectMapper;

    private String token;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) throws IOException {
        deleteRecursively(DATA_DIR);
        Files.createDirectories(DATA_DIR);
        registry.add("mailbus.data-dir", DATA_DIR::toString);
        registry.add("mailbus.layout-path",
                () -> Path.of("..", "config", "office-layout.json").toAbsolutePath().toString());
        registry.add("mailbus.metrics-manifest-path", () -> Path.of("..", "shared", "config",
                "mailbus", "metrics-manifest.json").toAbsolutePath().toString());
        registry.add("mailbus.dispatch-interval-seconds", () -> 3600);
        registry.add("mailbus.heartbeat-sweep-seconds", () -> 3600);
        registry.add("mailbus.stream-interval-ms", () -> 3600_000);
        registry.add("mailbus.token-encryption-key",
                () -> "test-only-token-encryption-key-32bytes");
    }

    @BeforeAll
    void bootstrap() throws Exception {
        MvcResult created = mvc.perform(post("/api/identity/bootstrap/super-admin")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"Root\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        token = json(created).path("token").asText();
    }

    @Test
    void agentUnbindIsIdempotentAndAllowsDelete() throws Exception {
        MvcResult position = mvc.perform(post("/api/positions").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"契约岗\",\"capabilities\":[]}"))
                .andExpect(status().isCreated())
                .andReturn();
        String positionId = json(position).path("position_id").asText();
        MvcResult invite = mvc.perform(post("/api/agent-invites").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"employee_name\":\"待解绑 Agent\",\"position_id\":\""
                                + positionId + "\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        MvcResult registered = mvc.perform(post("/api/agents/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + json(invite).path("invite_code").asText()
                                + "\",\"name\":\"待解绑 Agent\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode registration = json(registered);
        String agentId = registration.path("agent_id").asText();
        String employeeId = registration.path("employee_id").asText();

        mvc.perform(delete("/api/agents/" + agentId).with(auth()))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/agents/" + agentId + "/unbind").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.agent_id").value(agentId));
        mvc.perform(get("/api/employees/" + employeeId).with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.agent_id").value(nullValue()));
        mvc.perform(post("/api/agents/" + agentId + "/unbind").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.agent_id").value(agentId));
        mvc.perform(delete("/api/agents/" + agentId).with(auth()))
                .andExpect(status().isNoContent());
        mvc.perform(post("/api/agents/" + agentId + "/unbind").with(auth()))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/agents/agent_missing/unbind").with(auth()))
                .andExpect(status().isNotFound());
    }

    @Test
    void taskTraceUsesRunProjectionAndExistingVisibility() throws Exception {
        MvcResult created = mvc.perform(post("/api/tasks").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"可追迹任务\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode task = json(created);
        String taskId = task.path("task_id").asText();
        JsonNode run = task.path("runs").get(0);

        MvcResult initialResult = mvc.perform(get("/api/tasks/" + taskId + "/trace").with(auth()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task_id").value(taskId))
                .andReturn();
        JsonNode initial = json(initialResult);
        assertThat(kinds(initial)).containsExactly("task.created", "run.dispatched");
        JsonNode createdEvent = event(initial, "task.created");
        assertThat(createdEvent.path("at").asText()).isEqualTo(task.path("created_at").asText());
        assertThat(createdEvent.path("detail").path("title").asText()).isEqualTo("可追迹任务");
        assertThat(createdEvent.path("detail").path("state").asText()).isEqualTo("running");
        assertRunEvent(event(initial, "run.dispatched"), run, "running");

        mvc.perform(post("/api/tasks/" + taskId + "/nodes/free/result").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attempt_no\":1,\"result\":\"完成\"}"))
                .andExpect(status().isOk());
        MvcResult tracedResult = mvc.perform(get("/api/tasks/" + taskId + "/trace").with(auth()))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode traced = json(tracedResult);
        assertThat(kinds(traced)).containsExactly(
                "task.created", "run.dispatched", "run.started", "run.completed");
        List<Instant> timestamps = new ArrayList<>();
        traced.path("events").forEach(item -> timestamps.add(Instant.parse(item.path("at").asText())));
        assertThat(timestamps).isSorted();
        for (String kind : List.of("run.dispatched", "run.started", "run.completed")) {
            assertRunEvent(event(traced, kind), run, "done");
        }

        mvc.perform(get("/api/tasks/task_missing/trace").with(auth()))
                .andExpect(status().isNotFound());
        String staffToken = createStaffToken();
        mvc.perform(get("/api/tasks/" + taskId + "/trace").with(authToken(staffToken)))
                .andExpect(status().isForbidden());
    }

    private String createStaffToken() throws Exception {
        MvcResult invite = mvc.perform(post("/api/employees/invite").with(auth())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"display_name\":\"无任务范围员工\"}"))
                .andExpect(status().isOk())
                .andReturn();
        MvcResult accepted = mvc.perform(post("/api/invites/accept")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"invite_code\":\"" + json(invite).path("invite_code").asText()
                                + "\",\"display_name\":\"无任务范围员工\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        return json(accepted).path("token").asText();
    }

    private void assertRunEvent(JsonNode event, JsonNode run, String state) {
        assertThat(event.path("run_id").asText()).isEqualTo(run.path("run_id").asText());
        assertThat(event.path("node_id").asText()).isEqualTo(run.path("node_id").asText());
        assertThat(event.path("attempt_no").asInt()).isEqualTo(run.path("attempt_no").asInt());
        assertThat(event.path("detail").path("state").asText()).isEqualTo(state);
    }

    private List<String> kinds(JsonNode trace) {
        List<String> kinds = new ArrayList<>();
        trace.path("events").forEach(event -> kinds.add(event.path("kind").asText()));
        return kinds;
    }

    private JsonNode event(JsonNode trace, String kind) {
        for (JsonNode event : trace.path("events")) {
            if (kind.equals(event.path("kind").asText())) {
                return event;
            }
        }
        throw new AssertionError("缺少追迹事件：" + kind);
    }

    private RequestPostProcessor auth() {
        return authToken(token);
    }

    private RequestPostProcessor authToken(String value) {
        return request -> {
            request.addHeader("Authorization", "Bearer " + value);
            return request;
        };
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var walk = Files.walk(root)) {
            walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.delete(path);
                } catch (IOException exception) {
                    throw new RuntimeException(exception);
                }
            });
        }
    }
}
