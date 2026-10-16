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
        argv = wrapForRunTarget(card.runTarget(), argv);
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

    /**
     * run_target dispatch (python runtime_net counterpart, minimal): the argv
     * stays declarative; the wrapper adapts WHERE it runs, never rewrites it.
     *  - windows/linux: direct
     *  - wsl:           wsl -e <argv...>          (Ubuntu per project convention)
     *  - docker:        docker exec <container> <argv...>  (container from adapter_config)
     */
    public static List<String> wrapForRunTarget(String runTarget, List<String> argv) {
        if (runTarget == null || runTarget.isBlank() || "windows".equalsIgnoreCase(runTarget)
                || "linux".equalsIgnoreCase(runTarget)) {
            return argv;
        }
        if ("wsl".equalsIgnoreCase(runTarget)) {
            List<String> out = new ArrayList<>();
            out.add("wsl");
            out.add("-e");
            out.addAll(argv);
            return out;
        }
        if ("docker".equalsIgnoreCase(runTarget)) {
            // container name comes via adapter_config {"container": "..."} pre-merged
            // into argv[0] slot by the caller; here we only add the exec prefix
            List<String> out = new ArrayList<>();
            out.add("docker");
            out.add("exec");
            out.add(argv.get(0)); // first token = container id by convention
            out.addAll(argv.subList(1, argv.size()));
            // On a Windows host the docker engine lives in WSL (python runtime_net
            // topology): route through wsl -e unless a native docker.exe exists.
            if (dockerHostOnWsl()) {
                return concat(List.of("wsl", "-e"), out);
            }
            return out;
        }
        return argv;
    }

    private static List<String> concat(List<String> prefix, List<String> rest) {
        List<String> out = new ArrayList<>(prefix);
        out.addAll(rest);
        return out;
    }

    /** Probe: does the push executable exist on the card's run_target? (test-connection stage 1) */
    public LaunchResult probe(AgentCard card) {
        Map<String, Object> cfg = card.adapterConfig();
        Object rawArgv = cfg.get("push_argv");
        if (!(rawArgv instanceof List<?> list) || list.isEmpty()) {
            return new LaunchResult(false, -1, "", "no push_argv configured");
        }
        String exe = String.valueOf(list.get(0));
        String target = card.runTarget() == null ? "windows" : card.runTarget();
        // absolute/relative path with separators: check the file directly, no PATH lookup
        boolean hasSep = exe.contains("/") || exe.contains("\\") || exe.contains(java.io.File.separator);
        if (hasSep && !"wsl".equalsIgnoreCase(target) && !"docker".equalsIgnoreCase(target)) {
            java.nio.file.Path p = java.nio.file.Path.of(exe);
            return java.nio.file.Files.isRegularFile(p)
                    ? new LaunchResult(true, 0, exe, "")
                    : new LaunchResult(false, -1, "", "executable not found: " + exe);
        }
        List<String> check = switch (target) {
            case "wsl" -> List.of("wsl", "-e", "sh", "-c", "command -v " + shellQuote(exe));
            case "docker" -> dockerHostOnWsl()
                    ? List.of("wsl", "-e", "docker", "exec", String.valueOf(list.get(0)), "sh", "-c", "command -v " + shellQuote(String.valueOf(list.get(1))))
                    : List.of("docker", "exec", String.valueOf(list.get(0)), "sh", "-c", "command -v " + shellQuote(String.valueOf(list.get(1))));
            default -> List.of("cmd", "/C", "where", exe); // windows; linux callers use which
        };
        if ("linux".equalsIgnoreCase(target)) {
            check = List.of("sh", "-c", "command -v " + shellQuote(exe));
        }
        try {
            Process p = new ProcessBuilder(check).redirectErrorStream(true).start();
            boolean fin = p.waitFor(20, TimeUnit.SECONDS);
            String out = new String(p.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).trim();
            boolean ok = fin && p.exitValue() == 0;
            return new LaunchResult(ok, fin ? p.exitValue() : -1, out,
                    ok ? "" : "executable not found: " + exe);
        } catch (Exception e) {
            return new LaunchResult(false, -1, "", "probe failed: " + e.getMessage());
        }
    }

    private static boolean dockerHostOnWsl() {
        return System.getProperty("os.name", "").toLowerCase().contains("win")
                && !java.nio.file.Files.isRegularFile(java.nio.file.Path.of("C:/Program Files/Docker/Docker/resources/bin/docker.exe"));
    }

    private static String shellQuote(String s) {
        return "'" + s.replace("'", "'''") + "'";
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
