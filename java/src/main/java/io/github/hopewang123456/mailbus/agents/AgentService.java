package io.github.hopewang123456.mailbus.agents;

import io.github.hopewang123456.mailbus.auth.Actor;
import io.github.hopewang123456.mailbus.auth.Authz;
import io.github.hopewang123456.mailbus.common.ApiException;
import io.github.hopewang123456.mailbus.common.Ids;
import io.github.hopewang123456.mailbus.events.Outbox;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@Service
public class AgentService {

    private final AgentRepository repository;
    private final Ids ids;
    private final Outbox outbox;

    public AgentService(AgentRepository repository, Ids ids, Outbox outbox) {
        this.repository = repository;
        this.ids = ids;
        this.outbox = outbox;
    }

    public List<AgentDtos.AgentOut> listAll() {
        return repository.listAll().stream().map(AgentDtos.AgentOut::of).toList();
    }

    @Transactional
    public AgentDtos.AgentOut create(Actor actor, AgentDtos.AgentIn input) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        String name = input.name() == null ? "" : input.name().strip();
        if (name.isEmpty()) {
            throw ApiException.conflict("invalid_state", "Agent 名称不能为空");
        }
        Instant now = Instant.now();
        Agent agent = new Agent(ids.next("agent"), name,
                input.framework() == null ? "" : input.framework(),
                input.model(), input.endpoint(),
                input.enabled() == null || input.enabled(), now, now);
        repository.save(agent);
        outbox.enqueue("agents.agent_created", Map.of("agent_id", agent.agentId()));
        return AgentDtos.AgentOut.of(agent);
    }

    @Transactional
    public AgentDtos.AgentOut update(Actor actor, String agentId, Map<String, Object> fields) {
        Authz.require(actor, Authz.SYSTEM_CONFIG);
        Agent existing = repository.find(agentId)
                .orElseThrow(() -> ApiException.notFound("Agent 不存在"));
        String name = fields.containsKey("name") && fields.get("name") != null
                ? String.valueOf(fields.get("name")).strip() : existing.name();
        if (name.isEmpty()) {
            throw ApiException.unprocessable();
        }
        if (name.length() > 64) {
            throw ApiException.unprocessable();
        }
        if (fields.get("framework") != null && !(fields.get("framework") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("model") != null && !(fields.get("model") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("endpoint") != null && !(fields.get("endpoint") instanceof String)) {
            throw ApiException.unprocessable();
        }
        if (fields.get("enabled") != null && !(fields.get("enabled") instanceof Boolean)) {
            throw ApiException.unprocessable();
        }
        String framework = fields.containsKey("framework")
                ? nullable(fields.get("framework")) : existing.framework();
        if (framework != null && framework.length() > 64) {
            throw ApiException.unprocessable();
        }
        String model = fields.containsKey("model")
                ? nullable(fields.get("model")) : existing.model();
        String endpoint = fields.containsKey("endpoint")
                ? nullable(fields.get("endpoint")) : existing.endpoint();
        boolean enabled = fields.containsKey("enabled") && fields.get("enabled") != null
                ? Boolean.parseBoolean(String.valueOf(fields.get("enabled"))) : existing.enabled();
        Agent updated = new Agent(existing.agentId(), name,
                framework == null ? "" : framework, model, endpoint, enabled,
                existing.createdAt(), Instant.now());
        repository.save(updated);
        outbox.enqueue("agents.agent_updated", Map.of("agent_id", agentId));
        return AgentDtos.AgentOut.of(updated);
    }

    public String summaryName(String agentId) {
        return repository.find(agentId).map(Agent::name).orElse(null);
    }

    public String summaryFramework(String agentId) {
        return repository.find(agentId).map(Agent::framework).orElse(null);
    }

    public boolean exists(String agentId) {
        return repository.find(agentId).isPresent();
    }

    private String nullable(Object value) {
        return value == null ? null : String.valueOf(value);
    }
}
