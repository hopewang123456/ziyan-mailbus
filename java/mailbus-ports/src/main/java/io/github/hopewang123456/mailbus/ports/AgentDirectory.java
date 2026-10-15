package io.github.hopewang123456.mailbus.ports;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Agent card store + CLI launcher port (M3: frameworks adapters).
 *
 * push_argv is a DECLARATIVE argv array with a "{MSG}" slot — never a shell
 * string. That is the python codebuddy lesson: Windows shell quoting eats
 * long messages; argv arrays bypass the shell entirely.
 */
public interface AgentDirectory {

    record AgentCard(String id, String type, String runTarget, boolean enabled,
                     Map<String, Object> adapterConfig) {}

    void upsert(AgentCard card);

    Optional<AgentCard> findById(String id);

    List<AgentCard> findAll();

    /** Push a message to the agent's CLI. Returns process exit + output digest. */
    LaunchResult launch(String agentId, String message);

    /** test-connection stage 1: executable reachability on the card's run_target. */
    LaunchResult probe(AgentCard card);

    record LaunchResult(boolean ok, int exitCode, String outputDigest, String error) {}

    /** framework presets — argv templates per type (supersonic-style registry). */
    Map<String, List<String>> PRESETS = Map.of(
            "claude_code", List.of("claude", "-p", "{MSG}", "--output-format", "text"),
            "codex", List.of("codex", "exec", "{MSG}"),
            "hermes", List.of("hermes", "-p", "{MSG}"),
            "opencode", List.of("opencode", "run", "{MSG}"));
}
