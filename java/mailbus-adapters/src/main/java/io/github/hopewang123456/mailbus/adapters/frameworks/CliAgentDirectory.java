package io.github.hopewang123456.mailbus.adapters.frameworks;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.ports.AgentDirectory;

import java.io.IOException;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;

/**
 * SQLite-backed agent directory + generic CLI launcher.
 *
 * Push semantics (python pusher counterpart, at-least-once): the message is
 * substituted into the argv "{MSG}" slot and the process runs to completion
 * (bounded by timeout_s, default 300). No shell — ProcessBuilder argv only.
 */
public class CliAgentDirectory implements AgentDirectory {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public CliAgentDirectory(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Override
    public void upsert(AgentCard card) {
        jdbc.update("""
                INSERT INTO agent_cards (id, type, run_target, enabled, adapter_config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  type = excluded.type,
                  run_target = excluded.run_target,
                  enabled = excluded.enabled,
                  adapter_config = excluded.adapter_config,
                  updated_at = excluded.updated_at
                """,
                card.id(), card.type(), card.runTarget(), card.enabled() ? 1 : 0,
                writeConfig(card.adapterConfig()),
                java.time.Instant.now(clock).toString(), java.time.Instant.now(clock).toString());
    }

    @Override
    public Optional<AgentCard> findById(String id) {
        List<AgentCard> out = jdbc.query(
                "SELECT * FROM agent_cards WHERE id = ?", this::map, id);
        return out.stream().findFirst();
    }

    @Override
    public List<AgentCard> findAll() {
        return jdbc.query("SELECT * FROM agent_cards ORDER BY id", this::map);
    }

    @Override
    public LaunchResult launch(String agentId, String message) {
        AgentCard card = findById(agentId).orElse(null);
        if (card == null) {
            return new LaunchResult(false, -1, "", "no agent card: " + agentId);
        }
        if (!card.enabled()) {
            return new LaunchResult(false, -1, "", "agent disabled: " + agentId);
        }
        Map<String, Object> cfg = card.adapterConfig();
        Object rawArgv = cfg.get("push_argv");
        if (!(rawArgv instanceof List<?> list) || list.isEmpty()) {
            return new LaunchResult(false, -1, "", "no push_argv configured for " + agentId);
        }
        List<String> argv = new ArrayList<>();
        for (Object o : list) {
            String s = String.valueOf(o);
            if (s.contains("{MSG}")) {
                s = s.replace("{MSG}", message == null ? "" : message);
            }
            argv.add(s);
        }
        long timeoutSec = ((Number) cfg.getOrDefault("timeout_s", 300)).longValue();
        try {
            Process p = new ProcessBuilder(argv)
                    .redirectErrorStream(true)
                    .start();
            boolean finished = p.waitFor(timeoutSec, TimeUnit.SECONDS);
            if (!finished) {
                p.destroyForcibly();
                return new LaunchResult(false, -1, "", "timeout after " + timeoutSec + "s");
            }
            String out = new String(p.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            String digest = out.length() > 200 ? out.substring(0, 200) + "..." : out;
            int code = p.exitValue();
            return new LaunchResult(code == 0, code, digest, code == 0 ? "" : "exit " + code);
        } catch (IOException e) {
            return new LaunchResult(false, -1, "", "spawn failed: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new LaunchResult(false, -1, "", "interrupted");
        }
    }

    private AgentCard map(java.sql.ResultSet rs, int i) throws java.sql.SQLException {
        return new AgentCard(
                rs.getString("id"),
                rs.getString("type"),
                rs.getString("run_target"),
                rs.getInt("enabled") == 1,
                readConfig(rs.getString("adapter_config")));
    }

    private String writeConfig(Map<String, Object> cfg) {
        try {
            return JSON.writeValueAsString(cfg == null ? Map.of() : cfg);
        } catch (IOException e) {
            throw new UncheckedIOExceptionWrapper(e);
        }
    }

    private Map<String, Object> readConfig(String raw) {
        if (raw == null || raw.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            return JSON.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (IOException e) {
            throw new UncheckedIOExceptionWrapper(e);
        }
    }

    private static final class UncheckedIOExceptionWrapper extends RuntimeException {
        UncheckedIOExceptionWrapper(IOException cause) {
            super(cause);
        }
    }
}
