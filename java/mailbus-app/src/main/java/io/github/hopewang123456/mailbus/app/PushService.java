package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.ports.AgentDirectory;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.util.List;
import java.util.Map;

/**
 * M3 scan/push loop (python scan counterpart): for every enabled agent card
 * with a launcher config, push PENDING messages via the CLI (at-least-once,
 * python M2 first-dispatch idempotency semantics: PENDING -> PUSHED on
 * successful spawn, failed spawns stay PENDING for the next sweep).
 */
public class PushService {

    public record PushReport(int pushed, int failed) {}

    private final MessageRepository repository;
    private final AgentDirectory directory;
    private final MessageEventLog events;

    public PushService(MessageRepository repository, AgentDirectory directory, MessageEventLog events) {
        this.repository = repository;
        this.directory = directory;
        this.events = events;
    }

    public PushReport pushPending(String agent) {
        int pushed = 0, failed = 0;
        for (var m : repository.findByAgentAndState(agent, MessageState.PENDING)) {
            AgentDirectory.LaunchResult r = directory.launch(agent, m.content());
            if (r.ok()) {
                repository.save(m.withState(MessageState.PUSHED, java.time.Instant.now()));
                events.append(m.id(), agent, "pushed", MessageState.PENDING.name(),
                        MessageState.PUSHED.name(), abbreviate(r.outputDigest()));
                pushed++;
            } else {
                events.append(m.id(), agent, "push_failed", MessageState.PENDING.name(),
                        MessageState.PENDING.name(), r.error());
                failed++;
            }
        }
        return new PushReport(pushed, failed);
    }

    /** Directory-facing use cases for CLI/REST. */
    public static final class Cards {
        private final AgentDirectory directory;

        public Cards(AgentDirectory directory) {
            this.directory = directory;
        }

        public void add(String id, String type, String runTarget, Map<String, Object> adapterConfig) {
            Map<String, Object> cfg = adapterConfig == null || adapterConfig.isEmpty()
                    ? presetConfig(type)
                    : adapterConfig;
            directory.upsert(new AgentDirectory.AgentCard(id, type, runTarget, true, cfg));
        }

        public List<AgentDirectory.AgentCard> list() {
            return directory.findAll();
        }

        private static Map<String, Object> presetConfig(String type) {
            List<String> argv = AgentDirectory.PRESETS.get(type);
            if (argv == null) {
                return Map.of();
            }
            return Map.of("push_argv", argv, "timeout_s", 300);
        }
    }

    private static String abbreviate(String s) {
        if (s == null) return "";
        String one = s.replace("\n", " ").replace("\r", " ").trim();
        return one.length() > 120 ? one.substring(0, 120) + "..." : one;
    }
}
