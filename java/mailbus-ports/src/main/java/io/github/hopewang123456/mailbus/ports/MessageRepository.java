package io.github.hopewang123456.mailbus.ports;

import io.github.hopewang123456.mailbus.domain.message.MessageState;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Message repository port — application depends on this interface only;
 * concrete storage (SQLite via Flyway schema, in-memory for tests/demo)
 * binds in mailbus-boot (the single composition root).
 */
public interface MessageRepository {

    void save(MsgRecord record);

    /**
     * Import semantics: persist with preserved raw provenance; implementations
     * that own files must NOT overwrite an existing shard (migration idempotency).
     * Default forwards to plain save for indexes without raw support.
     */
    default void save(MsgRecord record, String rawJson) {
        save(record);
    }

    Optional<MsgRecord> findById(String id);

    List<MsgRecord> findByAgentAndState(String agent, MessageState state);

    /** Messages pending beyond the threshold — the timeout scan query (SQLite-indexed). */
    List<MsgRecord> findStalePending(String agent, Instant cutoff);

    long countUnread(String agent);

    /** Aggregated counts for status/stats endpoints (M2). */
    record AgentStateCount(String agent, String state, long count) {}

    default java.util.List<AgentStateCount> countByAgentAndState() {
        return java.util.List.of(); // indexes without aggregation support
    }
}
