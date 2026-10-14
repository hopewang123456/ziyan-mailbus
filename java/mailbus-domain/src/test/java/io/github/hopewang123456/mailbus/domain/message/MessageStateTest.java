package io.github.hopewang123456.mailbus.domain.message;

import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessageStateTest {

    @Test
    void pendingFlowsToPushedAndProcessing() {
        assertTrue(MessageState.PENDING.canTransitionTo(MessageState.PUSHED));
        assertTrue(MessageState.PENDING.canTransitionTo(MessageState.PROCESSING));
        assertFalse(MessageState.PENDING.canTransitionTo(MessageState.ARCHIVED));
    }

    @Test
    void terminalStatesAreFrozen() {
        for (MessageState terminal : new MessageState[]{MessageState.REJECTED, MessageState.ARCHIVED}) {
            assertTrue(terminal.isTerminal());
            for (MessageState next : MessageState.values()) {
                assertFalse(terminal.canTransitionTo(next), terminal + " -> " + next);
            }
        }
    }

    @Test
    void recordTransitionEnforcesFsm() {
        Instant now = Instant.parse("2026-10-14T12:00:00Z");
        MsgRecord pending = new MsgRecord("msg-1", "a", "b", "notice", "hi",
                MsgRecord.Priority.URGENT, MessageState.PENDING, now, now);
        MsgRecord done = pending.withState(MessageState.PROCESSING, now)
                .withState(MessageState.DONE, now);
        assertEquals(MessageState.DONE, done.state());
        assertThrows(IllegalStateException.class,
                () -> done.withState(MessageState.PENDING, now));
    }
}
