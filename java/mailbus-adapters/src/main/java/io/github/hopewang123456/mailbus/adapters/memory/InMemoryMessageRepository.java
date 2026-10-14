package io.github.hopewang123456.mailbus.adapters.memory;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import io.github.hopewang123456.mailbus.ports.MessageRepository;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * In-memory MessageRepository — the Java counterpart of the Python fakes
 * (build_fake_ports semantics). Backs `mailbus-j demo` and tests; production
 * binds the SQLite adapter in mailbus-boot instead.
 */
public class InMemoryMessageRepository implements MessageRepository {

    private final Map<String, MsgRecord> store = new ConcurrentHashMap<>();

    @Override
    public void save(MsgRecord record) {
        store.put(record.id(), record);
    }

    @Override
    public Optional<MsgRecord> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public List<MsgRecord> findByAgentAndState(String agent, MessageState state) {
        return store.values().stream()
                .filter(r -> r.toAgent().equals(agent) && r.state() == state)
                .sorted(Comparator.comparing(MsgRecord::createdAt))
                .collect(Collectors.toList());
    }

    @Override
    public List<MsgRecord> findStalePending(String agent, Instant cutoff) {
        return store.values().stream()
                .filter(r -> r.toAgent().equals(agent)
                        && r.state() == MessageState.PENDING
                        && r.createdAt().isBefore(cutoff))
                .sorted(Comparator.comparing(MsgRecord::createdAt))
                .collect(Collectors.toList());
    }

    @Override
    public long countUnread(String agent) {
        return store.values().stream()
                .filter(r -> r.toAgent().equals(agent) && !r.state().isTerminal())
                .count();
    }
}
