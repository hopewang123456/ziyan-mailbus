package io.github.hopewang123456.mailbus.adapters.frameworks;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.hopewang123456.mailbus.ports.AgentDirectory;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Imports python transport cards (access/transport/&lt;agent&gt;/transport.json,
 * schema mailbus-transport-v1) into java agent_cards.
 *
 * Cards carry identity + topology (framework / docker compose service), NOT
 * push argv — the python side derives argv in adapter code. Imported cards
 * therefore land DISABLED ("identity known, push not wired"); wire push_argv
 * and enable per card afterwards (agent-enable / settings).
 */
public class TransportCardImporter implements io.github.hopewang123456.mailbus.ports.AgentCardImporter {

    private final Path repoRoot;

    public TransportCardImporter(Path repoRoot) {
        this.repoRoot = repoRoot;
    }

    private static final ObjectMapper JSON = new ObjectMapper();

    @Override
    public List<Import> importFrom(Path repoRoot) {
        Path transportDir = this.repoRoot.resolve("access").resolve("transport");
        if (!Files.isDirectory(transportDir)) {
            throw new IllegalArgumentException("no access/transport under " + repoRoot);
        }
        List<Import> out = new ArrayList<>();
        try (var stream = Files.list(transportDir)) {
            for (Path dir : stream.filter(Files::isDirectory).sorted().toList()) {
                Path card = dir.resolve("transport.json");
                if (!Files.isRegularFile(card)) {
                    continue;
                }
                JsonNode n = JSON.readTree(Files.readString(card, StandardCharsets.UTF_8));
                String id = n.path("agent_id").asText("");
                String framework = n.path("framework").asText("none");
                if (id.isBlank()) {
                    continue;
                }
                JsonNode docker = n.path("docker");
                String composeService = docker.path("compose_service").asText("");
                Map<String, Object> cfg = new LinkedHashMap<>();
                String runTarget;
                String note;
                if (!composeService.isBlank()) {
                    runTarget = "docker";
                    cfg.put("container", composeService);
                    note = "docker:" + composeService;
                } else {
                    runTarget = "windows";
                    note = "host";
                }
                out.add(new Import(new AgentDirectory.AgentCard(
                        id, framework, runTarget, false, cfg), note));
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return out;
    }

    /** Adapter-side factory bean (stateless). */
    public static class Factory implements io.github.hopewang123456.mailbus.ports.AgentCardImporter.Factory {
        @Override
        public io.github.hopewang123456.mailbus.ports.AgentCardImporter forRoot(Path repoRoot) {
            return new TransportCardImporter(repoRoot);
        }
    }
}
