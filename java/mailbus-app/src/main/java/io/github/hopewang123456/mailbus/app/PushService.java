package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.ports.AgentDirectory;
import io.github.hopewang123456.mailbus.ports.MessageEventLog;
import io.github.hopewang123456.mailbus.ports.MessageInboxWriter;
import io.github.hopewang123456.mailbus.ports.MessageProjection;

import java.util.List;
import java.util.Map;

/**
 * M3 scan/push loop (python scan counterpart): for every enabled agent card
 * with a launcher config, push PENDING messages via the CLI (at-least-once,
 * python M2 first-dispatch idempotency semantics: PENDING -> PUSHED on
 * successful spawn, failed spawns stay PENDING for the next sweep).
 *
 * <p>D16 批3：消息源/写回都切到 python inbox.json（唯一 SoT）——读投影找 PENDING，
 * 成功后按 python pusher 语义置 pushed（pushed_count+1 / last_pushed_at）。
 */
public class PushService {

    public record PushReport(int pushed, int failed) {}

    private final MessageProjection projection;
    private final MessageInboxWriter writer;
    private final AgentDirectory directory;
    private final MessageEventLog events;

    public PushService(MessageProjection projection, MessageInboxWriter writer,
                       AgentDirectory directory, MessageEventLog events) {
        this.projection = projection;
        this.writer = writer;
        this.directory = directory;
        this.events = events;
    }

    public PushReport pushPending(String agent) {
        int pushed = 0, failed = 0;
        for (var view : projection.messagesOf(agent)) {
            var m = view.record();
            if (m.state() != MessageState.PENDING) {
                continue;
            }
            AgentDirectory.LaunchResult r = directory.launch(agent, m.content());
            if (r.ok()) {
                writer.markPushed(m.id());
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
