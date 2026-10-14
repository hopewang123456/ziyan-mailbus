package io.github.hopewang123456.mailbus.domain.message;

import java.time.Instant;

/**
 * Message record — immutable value object. Timestamps are UTC Instant only
 * (audit L2: no mixed timezone encodings). Ops metadata (stall counters,
 * re-push attempts) deliberately NOT here — belongs to the ops layer store.
 */
public record MsgRecord(
        String id,
        String toAgent,
        String fromAgent,
        String type,
        String content,
        Priority priority,
        MessageState state,
        Instant createdAt,
        Instant updatedAt) {

    public enum Priority { LOW, NORMAL, HIGH, URGENT }

    public MsgRecord withState(MessageState next, Instant when) {
        if (!state.canTransitionTo(next)) {
            throw new IllegalStateException("illegal transition " + state + " -> " + next + " for " + id);
        }
        return new MsgRecord(id, toAgent, fromAgent, type, content, priority, next, createdAt, when);
    }
}
